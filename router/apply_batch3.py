#!/usr/bin/env python3
"""Dry run, batch 3: links to ADD for the approved groups only. Nothing is written to any database.

Reads a product rollup (made with rollup_products.py, kits + the component-leaf fallback) and keeps:
  group A  Dresser  -> bedroom-furniture-dressers-and-chests   (same pair as batch 1, now also for multi-category rows)
           Barstool -> bar-furniture-bar-stools
  group D  rule kit_component_categories: the kit goes to Ashley's own component-skus-<room> category
  group C  rule navigable_categories: the category comes from the navigable categories of the product's raw items (follow Ashley). Package-rule rows
           (category from the config's package_rules, not from Ashley) are not in this group.
Add-only: a category the product already has is never listed, and neither is a pair already in reports/approved_batch.csv.
The 20 non-AMP Sectionals dropped by decision (same list as build_approved_batch.py) are skipped, which needs --dump to map product -> slug.
Held back, not in this script: any *-headboards category (the Bed -> headboards policy decision), component_sku rows and any component-skus-* slug that is not a kit (group D).

  python apply_batch3.py --rollup reports/product_rollup_onebuild_kits_comp.csv --dump onebuilddemo_for_router.sql
Writes reports/links_to_add_batch3.csv (product, category_slug, item_code, current_categories, group) and prints counts.
"""
import argparse, csv, collections as C, os
HERE = os.path.dirname(os.path.abspath(__file__))
DROPPED = set("""33003S1 33003S2 33004S1 33004S2 64106S1 A3000244A2 A3000244A3 A3000244A4 A3000244A5 A3000244A6
A3000244A7 A3000244A8 A3000662A1 A3000662A2 A3000662A3 A3000662A4 A3000662A5 A3000662A6 A3000662A7 PC59106S10""".split())
GROUP_A = {('Dresser', 'bedroom-furniture-dressers-and-chests'), ('Barstool', 'bar-furniture-bar-stools')}

def split(s): return [c.strip() for c in s.split('|') if c.strip()]

def pick_links(rows, already=frozenset(), dropped_products=frozenset()):
    out = []
    for r in rows:
        if r['state'] not in ('assigned', 'assigned_partial') or not r['category']: continue
        if r['product'] in dropped_products: continue
        have = set(split(r['current']))
        for slug in split(r['category']):
            if slug in have or (r['product'], slug) in already: continue
            if r['rule'] == 'kit_component_categories': group = 'D'
            elif (r['item_code'], slug) in GROUP_A: group = 'A'
            elif r['rule'] == 'navigable_categories' and not slug.startswith('component-skus') and not slug.endswith('headboards'): group = 'C'      # headboards stay held back (the Bed -> headboards policy decision), whatever the item code
            else: continue
            out.append((r['product'], slug, r['item_code'], r['current'], group))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rollup', required=True)
    ap.add_argument('--approved', default='reports/approved_batch.csv', help='pairs already in the approved batch are skipped (file may be missing)')
    ap.add_argument('--dump', default='onebuilddemo_for_router.sql', help='used only to find the products on the dropped-Sectionals list')
    ap.add_argument('--out', default='reports/links_to_add_batch3.csv')
    a = ap.parse_args()
    path = lambda p: p if os.path.isabs(p) else os.path.join(HERE, p)
    rows = list(csv.DictReader(open(path(a.rollup), encoding='utf-8-sig')))
    already = set()
    if os.path.exists(path(a.approved)):
        already = {(r['product'], r['category_slug']) for r in csv.DictReader(open(path(a.approved), encoding='utf-8-sig'))}
    from dumpreader import rows as dump_rows
    dropped = {p['uuid'] for p in dump_rows(path(a.dump), 'pim_products') if p['slug'] in DROPPED}
    add = pick_links(rows, already, dropped)
    print('DRY RUN - nothing is written to any database')
    for g in 'ACD':
        sub = [x for x in add if x[4] == g]
        print(f'group {g}: {len(sub)} links, {len({x[0] for x in sub})} distinct products')
        for cat, n in C.Counter(x[1] for x in sub).most_common(): print(f'  {n:4d}  {cat}')
    dup = [k for k, n in C.Counter((x[0], x[1]) for x in add).items() if n > 1]
    print(f'  ----\n  {len(add):4d}  links to add, {len({x[0] for x in add})} distinct products\n  duplicate product+category pairs: {len(dup)}')
    print(f'  skipped because already in {a.approved}: {len(already)} pairs on file')
    out = path(a.out)
    with open(out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['product', 'category_slug', 'item_code', 'current_categories', 'group']); w.writerows(add)
    print('wrote', out)

if __name__ == '__main__': main()