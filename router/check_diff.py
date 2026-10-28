"""For every variation marked 'different' in a variation rollup, report facts only:
is the variation's SKU a raw item linked to its product (pim_product_raw_items), and to the variation itself?
    python check_diff.py --dump onebuilddemo_for_router.sql --variation-rollup reports/variation_rollup_onebuild.csv
Writes reports/diff_check.csv."""
import argparse, csv, collections as C
from dumpreader import rows

ap = argparse.ArgumentParser()
ap.add_argument('--dump', required=True)
ap.add_argument('--variation-rollup', required=True)
ap.add_argument('--out', default='reports/diff_check.csv')
a = ap.parse_args()

raw_sku = {r['uuid']: r['sku'] for r in rows(a.dump, 'pim_raw_items')}
uuids_of = C.defaultdict(set)
for u, s in raw_sku.items(): uuids_of[s].add(u)
links = list(rows(a.dump, 'pim_product_raw_items'))
by_product = C.defaultdict(set); by_variation = C.defaultdict(set)
for l in links:
    by_product[l['product_id']].add(l['raw_item_id'])
    if l.get('variation_id'): by_variation[l['variation_id']].add(l['raw_item_id'])

out = []
for r in csv.DictReader(open(a.variation_rollup, encoding='utf-8-sig')):
    if r['sku_vs_product'] != 'different': continue
    u = uuids_of.get(r['sku'], set())
    out.append(dict(
        sku=r['sku'], name=r['name'], product=r['product'], item_code=r['item_code'],
        sku_pick=r['sku_pick'], product_categories=r['categories'],
        raw_items_with_this_sku=len(u),
        sku_linked_to_product=bool(u & by_product[r['product']]),
        sku_linked_to_variation=bool(u & by_variation[r['variation']]),
        product_linked_skus=' | '.join(sorted({raw_sku[x] for x in by_product[r['product']] if x in raw_sku}))))
with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
print(len(out), 'different variations')
print('sku linked to its product:', C.Counter(o['sku_linked_to_product'] for o in out))
print('sku linked to its variation:', C.Counter(o['sku_linked_to_variation'] for o in out))
print('wrote', a.out)