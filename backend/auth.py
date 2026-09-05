"""Single-owner authentication for the local Ledger service.

The module intentionally has no dependency on the HTTP server.  It stores a
password verifier and hashes of random bearer session tokens in SQLite.  The
server owns cookie, origin, and request plumbing; callers only need the small
public interface in ``docs/INTERFACES.md``.
"""

import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
import re
from datetime import datetime, timezone

try:  # ``python backend/server.py`` puts backend/ on sys.path.
    import db
except ImportError:  # package imports used by the test suite.
    from . import db


SESSION_TTL = 12 * 60 * 60
MAX_FAILURES = 5
RATE_WINDOW = 15 * 60
LOCKOUT_SECONDS = 15 * 60
PASSWORD_MIN_LENGTH = 12
TOKEN_BYTES = 32
MAX_SESSION_TTL = 30 * 24 * 60 * 60


def _now():
    return time.time()


def _utc(ts=None):
    return datetime.fromtimestamp(_now() if ts is None else ts, timezone.utc).isoformat()


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_ttl(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("session lifetime must be a number")
    if value <= 0 or value > MAX_SESSION_TTL:
        raise ValueError("session lifetime is outside the allowed range")
    return value


def _password_hash(password, salt=None):
    """Return a portable verifier string and salt.

    scrypt is preferred and available in supported CPython builds.  PBKDF2 is
    retained as a standard-library fallback for constrained Python builds.
    """
    if not isinstance(password, str):
        raise ValueError("password must be text")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
    salt = salt or secrets.token_bytes(16)
    try:
        value = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return "scrypt$16384$8$1$" + _b64(salt) + "$" + _b64(value), salt
    except (AttributeError, ValueError):
        value = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
        return "pbkdf2-sha256$600000$" + _b64(salt) + "$" + _b64(value), salt


def _verify_password(password, encoded):
    try:
        if not isinstance(password, str) or not isinstance(encoded, str):
            return False
        parts = encoded.split("$")
        if parts[0] == "scrypt" and len(parts) == 6:
            _, n, r, p, salt_s, value_s = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            salt, expected = _unb64(salt_s), _unb64(value_s)
            actual = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                    n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024)
        elif parts[0] == "pbkdf2-sha256" and len(parts) == 4:
            _, iterations, salt_s, value_s = parts[0], parts[1], parts[2], parts[3]
            salt, expected = _unb64(salt_s), _unb64(value_s)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                        int(iterations))
        else:
            return False
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, IndexError, OverflowError):
        return False


def _b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def init_schema():
    """Create auth tables and indexes. Safe to call during every startup."""
    c = db._conn()
    c.executescript("""
      CREATE TABLE IF NOT EXISTS auth_owner (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        password_hash TEXT NOT NULL,
        password_salt TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        expires_at REAL NOT NULL,
        last_seen_at TEXT NOT NULL,
        remote_addr TEXT,
        revoked_at TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);
      CREATE TABLE IF NOT EXISTS auth_login_limits (
        remote_addr TEXT PRIMARY KEY,
        window_started REAL NOT NULL,
        failures INTEGER NOT NULL DEFAULT 0,
        blocked_until REAL NOT NULL DEFAULT 0
      );
    """)
    c.commit()
    c.close()


def configured():
    init_schema()
    return bool(db.q1("SELECT 1 FROM auth_owner WHERE id=1"))


def _new_session(remote="", session_ttl=SESSION_TTL):
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = _now()
    session_ttl = _session_ttl(session_ttl)
    remote = remote if isinstance(remote, str) else ""
    db.ex("INSERT INTO auth_sessions(token_hash,created_at,expires_at,last_seen_at,remote_addr,revoked_at) "
          "VALUES(?,?,?,?,?,NULL)",
          (_token_hash(token), _utc(now), now + session_ttl, _utc(now), remote[:255],))
    return token


def setup(password, remote="", session_ttl=SESSION_TTL):
    """Set up the one owner and return a newly authenticated session token.

    Setup is intentionally one-shot.  The HTTP layer must enforce localhost
    for this operation; the module does not guess whether an address is safe.
    """
    init_schema()
    if configured():
        raise ValueError("owner is already configured")
    # Validate optional test/deployment overrides before committing the owner,
    # so an invalid lifetime cannot leave a half-configured installation.
    session_ttl = _session_ttl(session_ttl)
    encoded, salt = _password_hash(password)
    now = _utc()
    c = db._conn()
    try:
        c.execute("INSERT INTO auth_owner VALUES(1,?,?,?,?)", (encoded, _b64(salt), now, now))
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback()
        raise ValueError("owner is already configured")
    finally:
        c.close()
    return _new_session(remote, session_ttl)


def _rate_state(remote):
    key = (remote or "unknown")[:255]
    row = db.q1("SELECT * FROM auth_login_limits WHERE remote_addr=?", (key,))
    now = _now()
    if not row or now - row["window_started"] >= RATE_WINDOW:
        db.ex("INSERT OR REPLACE INTO auth_login_limits(remote_addr,window_started,failures,blocked_until) VALUES(?,?,0,0)",
              (key, now))
        return key, now, 0, 0
    return key, row["window_started"], row["failures"], row["blocked_until"]


def _record_failure(remote):
    key, started, failures, blocked = _rate_state(remote)
    failures += 1
    blocked = max(blocked, _now() + LOCKOUT_SECONDS) if failures >= MAX_FAILURES else blocked
    db.ex("UPDATE auth_login_limits SET failures=?,blocked_until=? WHERE remote_addr=?",
          (failures, blocked, key))


def _clear_failures(remote):
    key = (remote or "unknown")[:255]
    db.ex("DELETE FROM auth_login_limits WHERE remote_addr=?", (key,))


def login(password, remote="", session_ttl=SESSION_TTL):
    """Verify the owner password and return a random session token.

    All failure cases intentionally share ``ValueError`` so callers cannot
    distinguish an unconfigured owner, bad password, or temporary lockout.
    """
    init_schema()
    row = db.q1("SELECT password_hash FROM auth_owner WHERE id=1")
    # Run a verifier even before setup to keep the path less distinguishable.
    if not row:
        _password_hash("Ledger unavailable: placeholder password")
        raise ValueError("authentication unavailable")
    key, _, _, blocked_until = _rate_state(remote)
    if _now() < blocked_until:
        raise ValueError("too many login attempts; try again later")
    if not isinstance(password, str) or not _verify_password(password, row["password_hash"]):
        _record_failure(key)
        raise ValueError("invalid credentials")
    _clear_failures(key)
    return _new_session(remote, session_ttl)


def validate(token):
    """Return whether a session token is active and unexpired."""
    if not isinstance(token, str) or not token or len(token) > 512:
        return False
    init_schema()
    row = db.q1("SELECT expires_at,revoked_at FROM auth_sessions WHERE token_hash=?", (_token_hash(token),))
    if not row or row["revoked_at"] or _now() >= row["expires_at"]:
        if row and _now() >= row["expires_at"]:
            db.ex("DELETE FROM auth_sessions WHERE token_hash=?", (_token_hash(token),))
        return False
    db.ex("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (_utc(), _token_hash(token)))
    return True


def logout(token):
    if not isinstance(token, str) or not token or len(token) > 512:
        return
    init_schema()
    db.ex("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL", (_utc(), _token_hash(token)))


def cleanup_sessions():
    """Remove expired and revoked sessions; useful for a periodic maintenance task."""
    init_schema()
    db.ex("DELETE FROM auth_sessions WHERE expires_at<=? OR revoked_at IS NOT NULL", (_now(),))


def token_from_cookie(cookie_header, cookie_name="ledger_session"):
    """Extract one cookie value without exposing other cookie contents."""
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name == cookie_name:
            return value or None
    return None


def make_session_cookie(token, secure=False, max_age=SESSION_TTL, cookie_name="ledger_session"):
    """Build a restrictive Set-Cookie value for the server's response layer."""
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError("token required")
    attrs = [f"{cookie_name}={token}", "Path=/", "HttpOnly", "SameSite=Strict", f"Max-Age={int(max_age)}"]
    if secure:
        attrs.append("Secure")
    return "; ".join(attrs)
