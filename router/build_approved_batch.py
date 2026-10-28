#!/usr/bin/env python3
"""Combine the approved would_add batches into one CSV and re-run the pre-write checks.
Writes ONLY reports/approved_batch.csv. It never touches a database.

  python build_approved_batch.py --dump onebuilddemo_for_router.sql

Inputs (made by the dry runs):
  reports/links_to_add.csv        batch 1  (python apply_would_add.py)
  reports/links_to_add_kits.csv   batch 2  (python apply_kit_would_add.py, run with the beds rollup in place)
Exit code 1 if any hard check fails.
"""
import argparse, csv, os, sys
from dumpreader import rows

HERE = os.path.dirname(os.path.abspath(__file__))
# Decision on record: the 20 non-AMP Sectionals are dropped (Ashley's own category for each is Sectional Sofas, already linked).
DROPPED = set("""33003S1 33003S2 33004S1 33004S2 64106S1 A3000244A2 A3000244A3 A3000244A4 A3000244A5 A3000244A6
A3000244A7 A3000244A8 A3000662A1 A3000662A2 A3000662A3 A3000662A4 A3000662A5 A3000662A6 A3000662A7 PC59106S10""".split())

def read(path):
    return list(csv.DictReader(open(os.path.join(HERE, path), encoding='utf-8-sig')))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', required=True)
    ap.add_argument('--out', default='reports/approved_batch.csv')
    a = ap.parse_args()
    dump = a.dump if os.path.isabs(a.dump) else os.path.join(HERE, a.dump)

    b1, b2 = read('reports/links_to_add.csv'), read('reports/links_to_add_kits.csv')
    batch = [('1', r) for r in b1] + [('2', r) for r in b2]
    fails = []

    pairs = [(r['product'], r['category_slug']) for _, r in batch]
    dup = len(pairs) - len(set(pairs))
    if dup: fails.append(f'{dup} duplicate product+category pairs')

    pim = {r['uuid']: r['slug'] for r in rows(dump, 'pim_products')}
    live = {r['uuid'] for r in rows(dump, 'products')}
    cats = {c['slug']: c for c in rows(dump, 'categories')}
    pcats = {c['slug']: c for c in rows(dump, 'pim_categories')}
    parents = {c['parent_id'] for c in cats.values()}

    missing = [p for p, _ in pairs if p not in pim]
    if missing: fails.append(f'{len(missing)} products not in pim_products')
    nolive = [p for p, _ in pairs if p not in live]
    if nolive: fails.append(f'{len(nolive)} products not in the live products table')
    dropped = [p for p, _ in pairs if pim.get(p) in DROPPED]
    if dropped: fails.append(f'{len(dropped)} links belong to products on the drop list')
    for slug in sorted({s for _, s in pairs}):
        c = cats.get(slug)
        if not c: fails.append(f'category {slug}: not in categories'); continue
        if str(c['status']) != '1' or c['deleted_at'] not in ('None', '', None): fails.append(f'category {slug}: inactive or deleted')
        if c['id'] in parents: fails.append(f'category {slug}: is a parent, not a leaf')
        if slug not in pcats: fails.append(f'category {slug}: not in pim_categories')

    live_links = {(r['product_id'], r['category_id']) for r in rows(dump, 'product_categories')}
    pim_by_uuid = {c['uuid']: c['slug'] for c in pcats.values()}
    pim_links = {(r['product_id'], pim_by_uuid.get(r['category_id'])) for r in rows(dump, 'pim_product_categories')}

    out = []
    for b, r in batch:
        s = r['category_slug']
        lc, pc = cats.get(s, {}).get('uuid', ''), pcats.get(s, {}).get('uuid', '')
        out.append(dict(batch=b, product=r['product'], product_slug=pim.get(r['product'], ''), item_code=r['item_code'],
                        category_slug=s, live_category_id=lc, pim_category_id=pc,
                        exists_in_live=(r['product'], lc) in live_links, exists_in_pim=(r['product'], s) in pim_links))
    path = a.out if os.path.isabs(a.out) else os.path.join(HERE, a.out)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)

    n_live, n_pim = sum(o['exists_in_live'] for o in out), sum(o['exists_in_pim'] for o in out)
    print(f"batch 1: {len(b1)} links | batch 2: {len(b2)} links | total {len(out)} links, {len({p for p, _ in pairs})} distinct products")
    print(f"already in live product_categories: {n_live} | already in pim_product_categories: {n_pim}")
    ok_live = sum(1 for r in rows(dump, 'product_categories') if r['category_id'] in {c['uuid'] for c in cats.values()})
    ok_pim = sum(1 for r in rows(dump, 'pim_product_categories') if r['category_id'] in pim_by_uuid)
    print(f"id check: product_categories rows whose category_id resolves in categories: {ok_live}; pim_product_categories rows that resolve in pim_categories: {ok_pim}")
    print('wrote', path)
    if fails:
        print('FAILED CHECKS:'); [print('  -', x) for x in fails]; sys.exit(1)
    print('all hard checks passed (no duplicates, no drop-list products, categories valid, products exist)')

if __name__ == '__main__':
    main()