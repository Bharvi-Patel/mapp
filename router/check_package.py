"""Test the package rule: for every product whose item_code is in package_rules (vendors/ashley.yaml), compare the set category the rule gives it
with what the router decided for the product's own raw items (their navigable categories, mostly).
    python check_package.py [--db reports/shadow.db] [--dump dump_for_evidence.sql] [--vendor vendors/ashley.yaml] [--out reports/package_check.csv]
status per product:
  agree            the package category is one of the categories the pieces got      -> the rule is backed up by the pieces
  differ           the pieces got other (real) categories and not the package one   -> look at these: either the rule or the pieces are wrong
  only_components  every decided piece is a Component (or none was decided)         -> the pieces cannot say anything about the set category
Also shows what the site links the product to today, so you can see 'the rule is right' versus 'the site agrees with it'."""
import argparse, collections as C, csv, json, os, sqlite3

def compare(products, raw_of, decisions, package_rules, current):
    out = []
    for p, code in products.items():
        if code not in package_rules: continue
        pk = package_rules[code]; real, rules = set(), set()
        for rid in raw_of.get(p, []):
            d = decisions.get(rid)
            if not d or d[0] != 'assigned' or not d[1]: continue
            slugs = d[3] or [d[1]]
            if all(s.startswith('component-skus') for s in slugs): continue
            real |= {s for s in slugs if not s.startswith('component-skus')}; rules.add(d[2])
        status = 'only_components' if not real else ('agree' if pk in real else 'differ')
        out.append(dict(product=p, item_code=code, package_slug=pk, status=status, piece_slugs=' | '.join(sorted(real)),
                        piece_rules=' | '.join(sorted(rules)), current=' | '.join(sorted(current.get(p, ())))))
    return out

def main():
    import cascade as CA
    from dumpreader import rows
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='reports/shadow.db'); ap.add_argument('--dump', default='dump_for_evidence.sql')
    ap.add_argument('--vendor', default='vendors/ashley.yaml'); ap.add_argument('--out', default='reports/package_check.csv')
    a = ap.parse_args()
    cfg = CA.K.load_vendor_config(a.vendor)
    products = {p['uuid']: p['item_code'] for p in rows(a.dump, 'pim_products') if not p.get('deleted_at')}
    raw_of = C.defaultdict(list)
    for r in rows(a.dump, 'pim_product_raw_items'): raw_of[r['product_id']].append(r['raw_item_id'])
    conn = sqlite3.connect(a.db)
    try: dr = conn.execute("select subject_uuid, outcome, primary_slug, rule, slugs from router_decisions where status in ('shadow','applied') order by id").fetchall()
    except sqlite3.OperationalError: dr = [r + (None,) for r in conn.execute("select subject_uuid, outcome, primary_slug, rule from router_decisions where status in ('shadow','applied') order by id")]
    decisions = {u: (o, s, rule, json.loads(sl) if sl else None) for u, o, s, rule, sl in dr}
    slug = {c['uuid']: c['slug'] for c in rows(a.dump, 'pim_categories')}
    current = C.defaultdict(set)
    for r in rows(a.dump, 'pim_product_categories'):
        if r['category_id'] in slug: current[r['product_id']].add(slug[r['category_id']])
    res = compare(products, raw_of, decisions, cfg.get('package_rules') or {}, current)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
    print(f'{len(res)} package products\n')
    by = C.defaultdict(C.Counter)
    for r in res: by[r['item_code']][r['status']] += 1
    print(f'{"item code":32s} {"agree":>7s} {"differ":>7s} {"only_comp":>10s}')
    for code, c in sorted(by.items(), key=lambda kv: -sum(kv[1].values())): print(f'{code:32s} {c["agree"]:7d} {c["differ"]:7d} {c["only_components"]:10d}')
    tot = C.Counter(r['status'] for r in res); print(f'{"total":32s} {tot["agree"]:7d} {tot["differ"]:7d} {tot["only_components"]:10d}')
    d = C.Counter((r['item_code'], r['package_slug'], r['piece_slugs']) for r in res if r['status'] == 'differ').most_common(8)
    if d: print('\nmost common disagreements (item code, package category, what the pieces got):'); [print(f'  {n:4d}  {k}') for k, n in d]
    print(f'\nwrote {a.out}')

if __name__ == '__main__': main()