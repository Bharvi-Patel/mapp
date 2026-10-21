"""Give every pim_product_variation its product's categories (one or several), flag those with none, and check against the raw item with the same SKU.
Step 1, in DBeaver, run this and export the result grid as CSV to router/reports/variations.csv (columns: uuid, product_id, sku, name):
    SELECT v.uuid, v.product_id, v.sku, l.name
    FROM pim_product_variations v LEFT JOIN pim_product_variation_languages l ON l.variation_id = v.uuid;
Step 2, from the router folder (after rollup_products.py):
    python rollup_variations.py [--variations reports/variations.csv] [--rollup reports/product_rollup.csv] [--db reports/shadow.db]
Writes reports/variation_rollup.csv and prints counts. A variation takes ALL of its product's categories (the router's decision is per product).
Columns added: categories (every category, ' | ' separated), n_categories, uncategorized (True when the product gives it none)."""
import argparse, collections as C, csv, os, sqlite3

def split_cats(text):
    return [c.strip() for c in (text or '').split('|') if c.strip()]

def join(variations, products, sku_decisions):
    out = []
    for v in variations:
        p = products.get(v['product_id'])
        row = dict(variation=v['uuid'], sku=v['sku'], name=v.get('name', ''), product=v['product_id'],
                   item_code='', product_state='no_product_in_rollup', category='', categories='', n_categories=0, uncategorized=True,
                   rule='', sku_pick='', sku_vs_product='')
        if p:
            cats = split_cats(p['category'])                       # 'a | b' (a product whose pieces landed in several) -> ['a', 'b']
            row.update(item_code=p['item_code'], product_state=p['state'], category=p['category'], categories=' | '.join(cats),
                       n_categories=len(cats), uncategorized=not cats, rule=p['rule'])
            d = sku_decisions.get(v['sku'])
            if d and d[0] == 'assigned':
                row['sku_pick'] = d[1]
                if cats: row['sku_vs_product'] = 'same' if d[1] in cats else 'different'
            elif d: row['sku_pick'] = '(review)'
        out.append(row)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variations', default='reports/variations.csv'); ap.add_argument('--rollup', default='reports/product_rollup.csv')
    ap.add_argument('--db', default='reports/shadow.db'); ap.add_argument('--out', default='reports/variation_rollup.csv')
    a = ap.parse_args()
    variations = list(csv.DictReader(open(a.variations, encoding='utf-8-sig')))
    products = {r['product']: r for r in csv.DictReader(open(a.rollup, encoding='utf-8-sig'))}
    dec = {}
    if os.path.exists(a.db):
        for sku, outcome, slug in sqlite3.connect(a.db).execute(
                "select sku, outcome, primary_slug from router_decisions where status in ('shadow','applied') order by id"):
            dec[sku] = (outcome, slug)
    res = join(variations, products, dec)
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
    n = len(res); st = C.Counter(r['product_state'] for r in res)
    ok = sum(1 for r in res if not r['uncategorized'])
    multi = sum(1 for r in res if r['n_categories'] > 1)
    print(f'{n} variations, {len({r["product"] for r in res})} distinct products')
    for k, v in st.most_common(): print(f'  {k:22s} {v:6d}  {100*v/n:5.1f}%')
    print(f'\nvariations that get a category through their product: {ok} ({100*ok/n:.1f}%)   in several categories: {multi}   uncategorized: {n - ok}')
    print('by rule:', dict(C.Counter(r['rule'].split(':')[0] for r in res if not r['uncategorized']).most_common()))
    m = [r for r in res if r['sku_vs_product']]
    print(f'\nvariation SKU also a raw item with its own pick: {len(m)} ({100*len(m)/n:.1f}% of variations)')
    c = C.Counter(r['sku_vs_product'] for r in m); print('   same as the product category:', c['same'], '| different:', c['different'])
    diff = C.Counter((r['sku_pick'], r['category']) for r in m if r['sku_vs_product'] == 'different').most_common(8)
    if diff: print('   most common differences (SKU pick -> product category):', diff)
    print(f'wrote {a.out}')

if __name__ == '__main__':
    main()