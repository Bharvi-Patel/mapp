#!/usr/bin/env python3
"""Dry run, batch 4: links to ADD for component kits, following Ashley's own navigable categories.

Reads a rollup CSV (default reports/product_rollup.csv), keeps rows with rule == kit_component_categories and
vs_current == would_add. These are products Ashley files ONLY under Component SKUs (the 40 kit/component products and AMP003063):
they get the component-skus-<room> leaf and nothing else. Add-only: the room parent link the importer made stays.
apply_kit_would_add.py ignores these rows on purpose (it only takes kit_navigable_categories), so this script is the one that picks them up.

  python apply_component_would_add.py [--rollup reports/product_rollup_final3.csv]
Writes reports/links_to_add_components.csv. Nothing is written to any database.
"""
import argparse, csv, collections as C, os
HERE = os.path.dirname(os.path.abspath(__file__))

def split(s): return [c.strip() for c in s.split('|') if c.strip()]

def pick_links(rows):
    out = []
    for r in rows:
        if r['vs_current'] != 'would_add' or r['rule'] != 'kit_component_categories': continue
        have = set(split(r['current']))
        for slug in split(r['category']):
            if slug.startswith('component-skus-') and slug not in have:    # only the component leaf, never another category
                out.append((r['product'], slug, r['item_code'], r['current']))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--rollup', default=os.path.join(HERE, 'reports', 'product_rollup.csv'))
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.rollup, encoding='utf-8-sig')))
    add = pick_links(rows)
    print('DRY RUN - nothing is written to any database')
    for cat, n in C.Counter(x[1] for x in add).most_common(): print(f'  {n:4d}  {cat}')
    print(f'  ----\n  {len(add):4d}  links to add, {len({x[0] for x in add})} distinct products')
    print('  duplicate product+category pairs:', sum(1 for k, n in C.Counter((x[0], x[1]) for x in add).items() if n > 1))
    path = os.path.join(HERE, 'reports', 'links_to_add_components.csv')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['product', 'category_slug', 'item_code', 'current_categories'])
        w.writerows(add)
    print('wrote', path)

if __name__ == '__main__': main()