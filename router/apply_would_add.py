#!/usr/bin/env python3
"""Dry run: which product -> category links to ADD from the would_add rows (add only, nothing is written to any database).

Reads reports/product_rollup.csv and keeps only the approved batch:
  group 1  Dining Chair / Table Lamp Pair / Barstool / Vase -> the product-specific leaf (navigable_categories rule)
  group 2a Dresser -> bedroom-furniture-dressers-and-chests
Held back on purpose: Bed -> *-headboards (policy decision), the 13 odd Sectional/Accent Chair/Desk/Stool rows,
all component_sku rows (827), and the package_exception / name-match rows.

  python apply_would_add.py            prints counts per category, writes reports/links_to_add.csv
"""
import csv, collections as C, os
HERE = os.path.dirname(os.path.abspath(__file__))
APPROVED = {
    ('Dining Chair', 'dining-furniture-dining-room-chairs'),
    ('Table Lamp Pair', 'lighting-table-lamps'),
    ('Barstool', 'bar-furniture-bar-stools'),
    ('Vase', 'home-accents-vases-and-bottles'),
    ('Dresser', 'bedroom-furniture-dressers-and-chests'),
}

def pick_rows(rows):
    out = []
    for r in rows:
        if r['vs_current'] != 'would_add' or r['rule'] != 'navigable_categories': continue
        if (r['item_code'], r['category']) not in APPROVED: continue
        if r['category'] in {c.strip() for c in r['current'].split('|')}: continue   # already linked: never add twice
        out.append(r)
    return out

def main():
    rows = list(csv.DictReader(open(os.path.join(HERE, 'reports', 'product_rollup.csv'), encoding='utf-8-sig')))
    add = pick_rows(rows)
    by = C.Counter(r['category'] for r in add)
    print('DRY RUN - nothing is written to any database')
    for cat, n in by.most_common(): print(f'  {n:4d}  {cat}')
    print(f'  ----\n  {len(add):4d}  links to add, {len({r["product"] for r in add})} distinct products')
    dup = [p for p, n in C.Counter(r['product'] for r in add).items() if n > 1]
    print('  products appearing more than once:', len(dup))
    path = os.path.join(HERE, 'reports', 'links_to_add.csv')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['product', 'category_slug', 'item_code', 'current_categories'])
        for r in add: w.writerow([r['product'], r['category'], r['item_code'], r['current']])
    print('wrote', path)

if __name__ == '__main__': main()