#!/usr/bin/env python3
"""READ-ONLY. Finds out which table holds the product-to-category links the site uses.

Two candidates exist in the dump:
  A) pim_product_categories (product_id, category_id)  + pim_categories (uuid, slug)
  B) product_categories     (product_id, category_id)  + categories     (uuid, slug)
This script only runs SELECTs. It compares both against the products and slugs in
reports/links_to_add.csv and reports/links_to_add_kits.csv and prints facts, no verdict.

  python check_link_tables.py --db mysql://user:pass@host/dbname
Needs: pip install pymysql      Run from the router folder.
"""
import argparse, csv, os, collections as C
import dbconn

HERE = os.path.dirname(os.path.abspath(__file__))


def read_links(paths):
    out = []
    for p in paths:
        full = os.path.join(HERE, p)
        if not os.path.exists(full):
            print(f'  (missing, skipped: {p})'); continue
        with open(full, encoding='utf-8-sig', newline='') as f:
            out += [(r['product'], r['category_slug']) for r in csv.DictReader(f)]
    return out


def q(conn, ph, sql, params=()):
    try:
        return dbconn.fetch(conn, ph, sql, params)
    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        return f'ERROR: {e}'


def chunks(xs, n=500):
    xs = list(xs)
    for i in range(0, len(xs), n): yield xs[i:i + n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True, help='mysql://user:pass@host/dbname (the database the site uses)')
    ap.add_argument('--links', nargs='*', default=['reports/links_to_add.csv', 'reports/links_to_add_kits.csv'])
    a = ap.parse_args()

    links = read_links(a.links)
    prods = sorted({p for p, _ in links}); slugs = sorted({s for _, s in links})
    print(f'planned links: {len(links)}  distinct products: {len(prods)}  distinct slugs: {len(slugs)}\n')

    conn, ph = dbconn.connect(a.db)
    try:
        print('1) which tables exist')
        have = {r[0] for r in q(conn, ph, 'SHOW TABLES')} if not isinstance(q(conn, ph, 'SHOW TABLES'), str) else set()
        for t in ['pim_product_categories', 'pim_categories', 'pim_products', 'product_categories', 'categories', 'products']:
            print(f'   {t:24s} {"present" if t in have else "NOT FOUND"}')

        print('\n2) row counts')
        for t in ['pim_product_categories', 'product_categories']:
            if t in have: print(f'   {t:24s}', q(conn, ph, f'SELECT COUNT(*), COUNT(DISTINCT product_id) FROM {t}'))

        print('\n3) how many planned products appear in each link table (product_id)')
        for t in ['pim_product_categories', 'product_categories']:
            if t not in have: continue
            found = set()
            for ch in chunks(prods):
                res = q(conn, ph, f'SELECT DISTINCT product_id FROM {t} WHERE product_id IN ({",".join(["%s"] * len(ch))})', tuple(ch))
                if isinstance(res, str): print('  ', t, res); break
                found |= {r[0] for r in res}
            print(f'   {t:24s} {len(found)} of {len(prods)} products found')

        print('\n4) how many planned slugs exist in each category table (slug)')
        for t in ['pim_categories', 'categories']:
            if t not in have: continue
            res = q(conn, ph, f'SELECT slug FROM {t} WHERE slug IN ({",".join(["%s"] * len(slugs))})', tuple(slugs))
            if isinstance(res, str): print('  ', t, res); continue
            got = {r[0] for r in res}
            print(f'   {t:24s} {len(got)} of {len(slugs)} slugs found; missing: {sorted(set(slugs) - got) or "none"}')

        print('\n5) sample: current category slugs of 3 planned products, per table')
        for p in prods[:3]:
            print(f'   product {p}')
            for lt, ct in [('pim_product_categories', 'pim_categories'), ('product_categories', 'categories')]:
                if lt in have and ct in have:
                    res = q(conn, ph, f'SELECT c.slug FROM {lt} l JOIN {ct} c ON c.uuid = l.category_id WHERE l.product_id = %s', (p,))
                    print(f'     {lt:24s}', res if isinstance(res, str) else sorted(r[0] for r in res))
    finally:
        conn.close()
    print('\nRead-only: nothing was written.')


if __name__ == '__main__':
    main()