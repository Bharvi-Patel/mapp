#!/usr/bin/env python3
"""READ-ONLY. Compares the two link tables for the same products and for the planned links.

  A = pim_product_categories + pim_categories      B = product_categories + categories
Only SELECTs. Run from the router folder:
  python check_link_overlap.py --db "mysql://USER:PASS@HOST:PORT/DATABASE"
"""
import argparse, csv, os, collections as C
import dbconn

HERE = os.path.dirname(os.path.abspath(__file__))


def load(conn, ph, link, cat):
    sets, dups = C.defaultdict(set), 0
    rows = dbconn.fetch(conn, ph, f'SELECT l.product_id, c.slug FROM {link} l JOIN {cat} c ON c.uuid = l.category_id')
    seen = set()
    for p, s in rows:
        if (p, s) in seen: dups += 1
        seen.add((p, s)); sets[p].add(s)
    return sets, dups, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--links', nargs='*', default=['reports/links_to_add.csv', 'reports/links_to_add_kits.csv'])
    a = ap.parse_args()
    planned = []
    for p in a.links:
        with open(os.path.join(HERE, p), encoding='utf-8-sig', newline='') as f:
            planned += [(r['product'], r['category_slug'], p) for r in csv.DictReader(f)]

    conn, ph = dbconn.connect(a.db)
    try:
        A, dupA, nA = load(conn, ph, 'pim_product_categories', 'pim_categories')
        B, dupB, nB = load(conn, ph, 'product_categories', 'categories')
    finally:
        conn.close()
    print(f'A rows joined to a slug: {nA}, duplicate product+slug pairs: {dupA}')
    print(f'B rows joined to a slug: {nB}, duplicate product+slug pairs: {dupB}')

    both = set(A) & set(B)
    rel = C.Counter()
    for p in both:
        rel['same' if A[p] == B[p] else 'B has more' if A[p] < B[p] else 'A has more' if B[p] < A[p] else 'differ'] += 1
    print(f'\nproducts in both tables: {len(both)}  (only in A: {len(set(A) - set(B))}, only in B: {len(set(B) - set(A))})')
    print('for the products in both, B compared with A:', dict(rel))

    print('\nplanned links (224): is the slug already linked?')
    for f in sorted({x[2] for x in planned}):
        rows = [x for x in planned if x[2] == f]
        inA = sum(s in A.get(p, ()) for p, s, _ in rows)
        inB = sum(s in B.get(p, ()) for p, s, _ in rows)
        print(f'  {f}: {len(rows)} links; already in A: {inA}; already in B: {inB}; '
              f'missing from both: {sum(s not in A.get(p, ()) and s not in B.get(p, ()) for p, s, _ in rows)}')
    print('\nRead-only: nothing was written.')


if __name__ == '__main__':
    main()