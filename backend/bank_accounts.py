"""Prevent a second bank feed before creating an account or importing history.

Bank, environment and account suffix identify a collision regardless of the
chosen scope, display name, subtype or balance. Suffix collisions are refused,
never silently merged. Missing suffixes across connections fail closed when
the bank/type could already be present. Manual assets are outside this rule.
"""


def init_schema(c):
    if 'institution_id' not in {r[1] for r in c.execute('PRAGMA table_info(items)')}:
        c.execute('ALTER TABLE items ADD COLUMN institution_id TEXT')
    import transaction_repair
    transaction_repair.init_schema(c)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS bank_item_unique ON items(env,plaid_item_id) WHERE plaid_item_id IS NOT NULL AND plaid_item_id<>''")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS bank_feed_unique ON accounts(item_id,plaid_account_id) WHERE item_id IS NOT NULL AND plaid_account_id IS NOT NULL AND plaid_account_id<>''")
    # The same predicate backs the application checks and SQLite enforcement.
    for suffix, event in (("insert", "INSERT"), ("update", "UPDATE OF item_id,plaid_account_id,mask,type ON")):
        event_sql = "INSERT ON" if event == "INSERT" else event
        c.execute(f"""CREATE TRIGGER IF NOT EXISTS bank_account_{suffix}_guard
          BEFORE {event_sql} accounts
          WHEN NEW.item_id IS NOT NULL AND NOT EXISTS
            (SELECT 1 FROM transaction_account_aliases WHERE duplicate_account_id=NEW.id)
          BEGIN
            SELECT RAISE(ABORT,'Bank account already exists. Use the existing account connection.')
            WHERE EXISTS (
              SELECT 1 FROM accounts a JOIN items i ON i.id=a.item_id
              JOIN items incoming ON incoming.id=NEW.item_id
              WHERE a.id<>NEW.id AND i.env=incoming.env
              AND NOT EXISTS (SELECT 1 FROM transaction_account_aliases x WHERE x.duplicate_account_id=a.id)
              AND ((COALESCE(NEW.plaid_account_id,'')<>'' AND a.plaid_account_id=NEW.plaid_account_id)
                OR ((i.institution_id=incoming.institution_id OR lower(trim(i.institution))=lower(trim(incoming.institution))) AND (
                  (COALESCE(trim(NEW.mask),'')<>'' AND trim(a.mask)=trim(NEW.mask))
                  OR (a.item_id<>NEW.item_id AND
                      (COALESCE(trim(NEW.mask),'')='' OR COALESCE(trim(a.mask),'')='')
                      AND COALESCE(a.type,'')=COALESCE(NEW.type,'')))))
            );
          END""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS bank_alias_restore_guard
      BEFORE UPDATE OF archived ON accounts WHEN NEW.archived=0 AND EXISTS
      (SELECT 1 FROM transaction_account_aliases WHERE duplicate_account_id=NEW.id)
      BEGIN SELECT RAISE(ABORT,'This duplicate account was consolidated. Use its original account.'); END""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS bank_institution_update_guard
      BEFORE UPDATE OF institution,env,institution_id ON items
      WHEN lower(trim(NEW.institution))<>lower(trim(OLD.institution)) OR NEW.env<>OLD.env
        OR COALESCE(NEW.institution_id,'')<>COALESCE(OLD.institution_id,'')
      BEGIN SELECT RAISE(ABORT,'Changing this bank would duplicate an existing account.') WHERE EXISTS (
        SELECT 1 FROM accounts a JOIN accounts b ON a.item_id<>b.item_id
        JOIN items i ON i.id=b.item_id
        WHERE a.item_id=NEW.id AND i.env=NEW.env AND
          (i.institution_id=NEW.institution_id OR lower(trim(i.institution))=lower(trim(NEW.institution)))
        AND COALESCE(trim(a.mask),'')<>'' AND trim(a.mask)=trim(b.mask)
        AND NOT EXISTS (SELECT 1 FROM transaction_account_aliases x WHERE x.duplicate_account_id IN (a.id,b.id))
      ); END""")


def collision(c, item_id, provider):
    """Return the saved identity; never transfer a different feed's transactions."""
    incoming=c.execute('SELECT institution,env,institution_id FROM items WHERE id=?',(item_id,)).fetchone()
    mask=str(provider.get('mask') or '').strip()
    rows=c.execute("""SELECT a.* FROM accounts a JOIN items i ON i.id=a.item_id
      WHERE i.env=? AND NOT EXISTS
        (SELECT 1 FROM transaction_account_aliases x WHERE x.duplicate_account_id=a.id)
      AND (a.plaid_account_id=? OR ((i.institution_id=? OR lower(trim(i.institution))=lower(trim(?))) AND (
        (?<>'' AND trim(a.mask)=?) OR
        (a.item_id<>? AND (?='' OR COALESCE(trim(a.mask),'')='') AND COALESCE(a.type,'')=?))))
      ORDER BY (SELECT count(*) FROM transactions t WHERE t.account_id=a.id) DESC,a.created_at,a.id""",
      (incoming['env'],provider['account_id'],incoming['institution_id'],incoming['institution'],mask,mask,item_id,mask,provider.get('type') or '')).fetchall()
    if not rows: return None
    if len(rows)>1 or not mask:
        raise ValueError('This bank may already be linked. Reconnect the existing connection to avoid duplicate accounts.')
    saved=dict(rows[0])
    if not saved.get('mask'):
        raise ValueError('This bank may already be linked. Reconnect the existing connection to avoid duplicate accounts.')
    return saved
