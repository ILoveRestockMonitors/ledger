"""Direct Amazon Business sign-in and scheduled report sync, independent of Codex."""
import atexit
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime
from contextvars import copy_context
from pathlib import Path

import amazon_business
import db

_lock = threading.RLock()
_rpc_lock = threading.Lock()
_process = None
_process_dir = None
_output = None
_busy = False
_last_attempt = 0.0
_progress = None
_owner_dir = None
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'amazon-business-browser.mjs'


def directory():
    root = Path(db._paths()[0]).resolve() / 'amazon-business'
    return root


def _read(name, default):
    try: return json.loads((directory() / name).read_text())
    except (OSError, ValueError): return default


def _write(name, value):
    root = directory(); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / name
    temporary = root / (name + '.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
        json.dump(value, stream)
    temporary.replace(path)


def status():
    saved = _read('status.json', {})
    connected = bool(saved.get('connected'))
    with _lock:
        current = dict(_progress or {}) if _owner_dir == str(directory()) else {}
        busy = _busy and _owner_dir == str(directory())
    saved.update(current)
    ready = bool(saved.get('last_sync')) and ((directory() / 'charges.json').is_file() or (directory() / 'name_charges.json').is_file())
    return {'available': bool(shutil.which(os.environ.get('LEDGER_NODE', 'node')) and SCRIPT.is_file()),
            'connected': connected, 'ready': ready, 'busy': busy,
            'stage': saved.get('stage', 'disconnected'),
            'message': saved.get('message', 'Connect your Amazon Business account to match card charges and item names.'),
            'last_sync': saved.get('last_sync'), 'charges': saved.get('charges', 0),
            'named_transactions': saved.get('named_transactions', 0),
            'rejected_charges': saved.get('rejected_charges', 0),
            'captcha_image': saved.get('captcha_image'), 'codex_required': False}


def _stop():
    global _process, _output, _process_dir
    if _process:
        try:
            _process.terminate(); _process.wait(timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            try: _process.kill(); _process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired): pass
    _process = _output = _process_dir = None


atexit.register(_stop)


def _rpc(action, data=None):
    global _process, _output, _process_dir
    with _rpc_lock:
        if _process and (_process.poll() is not None or _process_dir != str(directory())): _stop()
        if not _process:
            node = shutil.which(os.environ.get('LEDGER_NODE', 'node'))
            if not node or not SCRIPT.is_file(): raise ValueError('The direct Amazon browser is unavailable on this server.')
            root = directory(); root.mkdir(parents=True, mode=0o700, exist_ok=True)
            env = {k:v for k,v in os.environ.items() if k in ('PATH', 'HOME', 'DISPLAY', 'PLAYWRIGHT_BROWSERS_PATH', 'NODE_PATH', 'SYSTEMROOT', 'TEMP', 'TMP')}
            env['LEDGER_AMAZON_DIR'] = str(root)
            _process = subprocess.Popen([node, str(SCRIPT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', env=env)
            _process_dir = str(root); _output = queue.Queue()
            process, output = _process, _output
            def receive():
                try:
                    for line in process.stdout:
                        if len(line) > 18_000_000: break
                        output.put(line)
                finally: output.put(None)
            threading.Thread(target=receive, daemon=True).start()
        try:
            _process.stdin.write(json.dumps({'action': action, **(data or {})}) + '\n'); _process.stdin.flush()
            line = _output.get(timeout=210 if action == 'sync' else 75)
            if not line: raise ValueError('The Amazon browser stopped. Reconnect and try again.')
            result = json.loads(line)
            if not isinstance(result, dict): raise ValueError('Amazon returned an unreadable response.')
            if result.get('error'): raise ValueError('Amazon could not complete this step. Reconnect or check the sign-in verification prompt.')
            return result
        except (OSError, queue.Empty, ValueError):
            _stop()
            raise ValueError('Amazon could not finish this step. Check your sign-in or try again.') from None


def _set_progress(value):
    global _progress
    with _lock: _progress = value


def command(action, data=None):
    """Start bounded work off the HTTP thread. Credentials never enter the command line."""
    global _busy, _owner_dir, _last_attempt
    data = dict(data or {})
    if action not in ('connect', 'verify', 'refresh', 'sync', 'disconnect', 'import'):
        raise ValueError('Choose a valid Amazon connection action.')
    if action == 'connect':
        if not isinstance(data.get('email'), str) or not 3 <= len(data['email']) <= 254:
            raise ValueError('Enter your Amazon Business email or phone number.')
        if not isinstance(data.get('password'), str) or not 1 <= len(data['password']) <= 1024:
            raise ValueError('Enter your Amazon password.')
        if type(data.get('remember', True)) is not bool: raise ValueError('Choose whether to remember your sign-in.')
        data = {k:data[k] for k in ('email','password','remember') if k in data}
    elif action == 'verify':
        code = data.get('code')
        if not isinstance(code, str) or not 1 <= len(code.strip()) <= 64: raise ValueError('Enter the verification code or characters from Amazon.')
        data = {'code': code.strip()}
    elif action == 'import':
        with _lock:
            if _busy: raise ValueError('Amazon is already working. Wait for this step to finish.')
            _save_report(amazon_business.parse_report(data.get('csv')))
            _set_progress(None)
            return status()
    else: data = {}
    with _lock:
        if _busy: raise ValueError('Amazon is already working. Wait for this step to finish.')
        if action in ('connect', 'verify') and time.monotonic() - _last_attempt < 2:
            raise ValueError('Wait a moment before trying the next sign-in step.')
        _last_attempt = time.monotonic(); _busy = True; _owner_dir = str(directory())
        if action == 'connect':
            _write('status.json', {'connected':False, 'stage':'disconnected', 'message':'Amazon sign-in is being updated.'})
            (directory() / 'charges.json').unlink(missing_ok=True)
            (directory() / 'name_charges.json').unlink(missing_ok=True)
        _set_progress({'stage': 'working', 'message': 'Reading Amazon Business orders and charges…' if action == 'sync' else 'Connecting to Amazon Business…'})
    def perform():
        global _busy
        sync_after_login = False
        try:
            if action == 'disconnect':
                with _rpc_lock: _stop()
                root = directory()
                if root.is_symlink() or root.resolve().parent != Path(db._paths()[0]).resolve(): raise ValueError('Amazon data location is invalid.')
                if root.exists(): shutil.rmtree(root)
                _set_progress(None)
                return
            result = _rpc(action, data)
            csv_text = result.pop('csv', None)
            direct_charges = amazon_business.sanitize_direct_charges(result.pop('direct_charges', None))
            if csv_text or direct_charges:
                parsed = amazon_business.parse_report(csv_text) if csv_text else {'charges': [], 'name_charges': [], 'rejected_charges': 0}
                _save_report(parsed, direct_charges=direct_charges)
            saved = _read('status.json', {})
            saved.update({k: result[k] for k in ('connected','stage','message') if k in result and not (k == 'message' and (csv_text or direct_charges))})
            # Challenge images stay in memory, not logs or synced state.
            _write('status.json', saved)
            _set_progress({'captcha_image': result.get('captcha_image')})
            if result.get('connected') and action in ('connect','verify','refresh'):
                sync_after_login = True
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else 'Amazon could not complete this step. Try reconnecting.'
            _set_progress({'stage': 'attention', 'message': message, 'captcha_image': None})
        finally:
            data.clear()
            with _lock: _busy = False
            if sync_after_login:
                try: command('sync')
                except ValueError: pass
    operation_context = copy_context()
    threading.Thread(target=lambda: operation_context.run(perform), daemon=True).start()
    return status()


def apply_saved_names():
    """Match saved Amazon charges against SQLite transactions to populate item names."""
    pool = _read('name_charges.json', None)
    if pool is None:
        pool = _read('charges.json', [])
    if not pool:
        return 0
    conn = db._conn()
    try:
        with conn:
            return amazon_business.apply_matched_names(conn, pool)
    finally:
        conn.close()


def _save_report(parsed, direct_charges=None):
    charges = list(parsed.get('charges') or [])
    name_charges = list(parsed.get('name_charges') or charges)
    seen_keys = {(c.get('charge_identifier'), tuple(c.get('orders') or ()), c.get('amount_cents'), c.get('posted')) for c in name_charges}
    for extra in (direct_charges or []):
        ekey = (extra.get('charge_identifier'), tuple(extra.get('orders') or ()), extra.get('amount_cents'), extra.get('posted'))
        if ekey not in seen_keys:
            name_charges.append(extra)
            seen_keys.add(ekey)
            if extra.get('card_last4') and sum(i.get('amount_cents', 0) for i in extra.get('items', [])) == extra.get('amount_cents'):
                charges.append(extra)
    _write('charges.json', charges)
    _write('name_charges.json', name_charges)
    named = apply_saved_names()
    saved = _read('status.json', {})
    total_known = len(name_charges)
    detail_note = f" ({named} transactions named)" if named else ""
    saved.update({
        'stage': 'connected' if saved.get('connected') else 'disconnected',
        'last_sync': datetime.now().isoformat(timespec='seconds'),
        'charges': total_known,
        'named_transactions': named,
        'rejected_charges': parsed.get('rejected_charges', 0),
        'message': f'Amazon Business synced{detail_note}. Matched purchases now show what you bought.',
    })
    _write('status.json', saved)
    # Resume Amazon lookups needing evidence; retain dismissed/applied jobs.
    if db.q1("SELECT 1 FROM sqlite_master WHERE type='table' AND name='receipt_jobs'"):
        db.ex("UPDATE receipt_jobs SET status='queued',message='',updated_at=? WHERE provider='amazon' AND status IN ('needs_user','failed')", (datetime.now().isoformat(timespec='seconds'),))


def tick():
    s = status()
    if s['connected'] and not s['busy']:
        try: age = time.time() - datetime.fromisoformat(s['last_sync']).timestamp()
        except (ValueError, TypeError): age = 1e9
        if age > 6 * 3600 and time.monotonic() - _last_attempt > 15 * 60:
            command('sync')


def investigate(job):
    if os.environ.get('LEDGER_DEMO') == '1':
        return {'payload': {'status':'failed', 'message':'Amazon sync is off in sample mode.'}, 'verified':False}
    tx = job['transaction']
    full_tx = db.q1("SELECT t.*, a.mask account_mask, a.iso_currency FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id WHERE t.id=?", (tx['id'],)) or tx
    charge, method = amazon_business.select_charge(full_tx, _read('charges.json', []))
    if not charge:
        # Even if item-level tax split is unavailable, check if name_charges can name the purchase.
        name_charge, name_method = amazon_business.select_charge(full_tx, _read('name_charges.json', []), allow_cardless=True)
        if name_charge:
            apply_saved_names()
            label = amazon_business.format_purchase_name(name_charge.get('items') or [])
            return {'payload': {'status': 'needs_user', 'message': f'Named purchase "{label}". Item tax/discount split differs from card total, so category stays unchanged.'}, 'verified': False}
        message = 'More than one Amazon charge could match; review the report.' if method == 'ambiguous' else 'No complete matching charge is in the synced Amazon Business report. Sync a report covering this payment date.'
        return {'payload': {'status':'needs_user', 'message':message}, 'verified':False}
    # A shared charge reference must also identify a single bank record.
    peers = db.q('''SELECT t.*,a.mask account_mask,a.iso_currency FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id
                    WHERE t.id<>? AND t.pending=0 AND t.is_transfer=0 AND t.amount<0 AND COALESCE(a.archived,0)=0
                      AND t.amount=? AND ABS(julianday(t.posted)-julianday(?))<=7''', (tx['id'],tx['amount'],tx['posted']))
    for peer in peers:
        selected, peer_method = amazon_business.select_charge(peer, [charge])
        if selected and (method != 'charge_identifier' or peer_method == 'charge_identifier'):
            return {'payload': {'status':'needs_user','message':'This Amazon charge could match more than one bank transaction. Review the duplicate candidates first.'}, 'verified':False}
    return {'payload': {'status':'matched', 'message':'Matched Amazon Business charge reference.' if method == 'charge_identifier' else 'Amount, card and date match; review before applying.',
                        'proposal':amazon_business.proposal(full_tx, charge, method)}, 'verified':True}
