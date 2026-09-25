import json
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from category_consolidation import consolidate


class ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.execute('PRAGMA foreign_keys=ON')
        self.c.executescript('''
          CREATE TABLE categories(id TEXT PRIMARY KEY,name TEXT UNIQUE,kind TEXT,tax_deductible INTEGER);
          CREATE TABLE transactions(id TEXT PRIMARY KEY,category_id TEXT REFERENCES categories(id),amount REAL);
          CREATE TABLE budgets(id TEXT PRIMARY KEY,category_id TEXT REFERENCES categories(id),scope TEXT,period TEXT,month_limit REAL);
          CREATE TABLE receipts(id TEXT PRIMARY KEY,original_category_id TEXT,category_id TEXT REFERENCES categories(id),proposal TEXT);
          CREATE TABLE category_edit_batches(id TEXT PRIMARY KEY,payload TEXT);
        ''')
        self.c.executemany('INSERT INTO categories VALUES(?,?,?,?)', [
          ('cat-shopping','Shopping','expense',0),('import-shopping','Shopping (other)','expense',0),
          ('health','Healthcare','expense',0),('medical','Medical','expense',0),
          ('gym','Gym','expense',0),('fitness','Health & Fitness','expense',0),
          ('biz','Business Travel','expense',1),('travel','Travel','expense',0),
          ('normalized','  SHOPPING  ','expense',0),('tax-shopping','shopping','expense',1)])

    def tearDown(self):
        self.c.close()

    def test_merge_preserves_money_references_and_undo(self):
        self.c.executemany('INSERT INTO transactions VALUES(?,?,?)',[('t1','cat-shopping',-47.99),('t2','import-shopping',-9.99)])
        self.c.executemany('INSERT INTO budgets VALUES(?,?,?,?,?)',[
          ('b1','cat-shopping','personal','monthly',20.10),('b2','import-shopping','personal','monthly',200.20),
          ('b3','import-shopping','business','monthly',50),('b4','import-shopping','all','monthly',80)])
        self.c.execute('INSERT INTO receipts VALUES(?,?,?,?)',('r','import-shopping','import-shopping',json.dumps({'items':[{'category_id':'import-shopping'}]})))
        self.c.execute('INSERT INTO category_edit_batches VALUES(?,?)',('edit',json.dumps({'before':{'category_id':'import-shopping'}})))
        with self.c: aliases=consolidate(self.c)
        self.assertEqual(aliases['import-shopping'],'cat-shopping')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],2)
        self.assertAlmostEqual(self.c.execute('SELECT SUM(amount) FROM transactions').fetchone()[0],-57.98)
        self.assertEqual({r[0] for r in self.c.execute('SELECT category_id FROM transactions')},{'cat-shopping'})
        self.assertEqual([(r['scope'],r['month_limit']) for r in self.c.execute('SELECT * FROM budgets ORDER BY id')],[('personal',220.30),('business',50),('all',80)])
        self.assertEqual(self.c.execute('SELECT original_category_id FROM receipts').fetchone()[0],'cat-shopping')
        self.assertNotIn('import-shopping',self.c.execute('SELECT payload FROM category_edit_batches').fetchone()[0])
        self.assertNotIn('import-shopping',self.c.execute('SELECT proposal FROM receipts').fetchone()[0])
        self.assertEqual(list(self.c.execute('PRAGMA foreign_key_check')),[])
        self.assertEqual(consolidate(self.c),{})

    def test_distinct_categories_and_tax_semantics_remain(self):
        consolidate(self.c)
        ids={r[0] for r in self.c.execute('SELECT id FROM categories')}
        self.assertTrue({'gym','fitness','health','biz','travel','tax-shopping'} <= ids)
        self.assertNotIn('medical',ids)
        self.assertNotIn('normalized',ids)

    def test_restart_does_not_recreate_duplicate_default(self):
        self.c.executemany('INSERT INTO categories VALUES(?,?,?,?)',[('cat-dining','Dining & Coffee','expense',0),('eat','Eat out','expense',0)])
        consolidate(self.c)
        self.c.execute("INSERT OR IGNORE INTO categories VALUES('cat-dining','Dining & Coffee','expense',0)")
        self.assertEqual(consolidate(self.c),{})
        self.assertEqual(self.c.execute("SELECT name FROM categories WHERE id='cat-dining'").fetchone()[0],'Eat out')

if __name__ == '__main__': unittest.main()
