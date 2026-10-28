#!/usr/bin/env python3
"""Dry run, batch 2: links to ADD for kits, using Ashley's own categories for the kit.

Reads reports/product_rollup.csv, keeps rows with rule == kit_navigable_categories and vs_current == would_add.
The category column can hold several slugs separated by ' | ': split them, drop any the product already has.
Held back on purpose: component_sku rows, navigable_categories Sectional/Desk rows (pieces' categories).

  python apply_kit_would_add.py        prints counts per category, writes reports/links_to_add_kits.csv
Nothing is written to any database.
"""
import csv, collections as C, os
HERE = os.path.dirname(os.path.abspath(__file__))

def split(s): return [c.strip() for c in s.split('|') if c.strip()]

def pick_links(rows):
    out = []
    for r in rows:
        if r['vs_current'] != 'would_add' or r['rule'] != 'kit_navigable_categories': continue
        have = set(split(r['current']))
        for slug in split(r['category']):
            if slug not in have:
                out.append((r['product'], slug, r['item_code'], r['current']))
    return out

def main():
    rows = list(csv.DictReader(open(os.path.join(HERE, 'reports', 'product_rollup.csv'), encoding='utf-8-sig')))
    add = pick_links(rows)
    print('DRY RUN - nothing is written to any database')
    for cat, n in C.Counter(a[1] for a in add).most_common(): print(f'  {n:4d}  {cat}')
    print(f'  ----\n  {len(add):4d}  links to add, {len({a[0] for a in add})} distinct products')
    dup = [k for k, n in C.Counter((a[0], a[1]) for a in add).items() if n > 1]
    print('  duplicate product+category pairs:', len(dup))
    path = os.path.join(HERE, 'reports', 'links_to_add_kits.csv')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['product', 'category_slug', 'item_code', 'current_categories'])
        w.writerows(add)
    print('wrote', path)

if __name__ == '__main__': main()