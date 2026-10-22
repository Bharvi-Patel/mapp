"""Roll the raw-item decisions up to PRODUCTS (the unit that has category links on the site). Run from the router folder
after a shadow run:
    python rollup_products.py [--db reports/shadow.db] [--dump dump_for_evidence.sql]
Per product:
  - item_code in package_rules (Bedroom Package, Dining Package ...)  -> its set category (package rule, same as the router's)
  - otherwise the decisions of its raw items. Component pieces (component-skus-*) are set aside when the product has a
    real category from another piece; if all assigned pieces agree the product takes that category.
States: assigned | assigned_partial (some pieces still in review) | keep_current (only with --keep-current-components: every piece is a Component, so the product keeps
        the categories it has today; off by default, because Ashley's navigable categories for those pieces ARE the component categories) | conflict (pieces disagree) | review | no_raw_item | not_in_run
Writes reports/product_rollup.csv and prints counts, plus how often the pick is already one of the product's current categories."""
import argparse, collections as C, csv, os, re, sqlite3

def _tokens(text):
    return {(t[:-1] if t.endswith('s') and len(t) > 3 else t) for t in re.split(r'[^a-z0-9]+', (text or '').lower()) if t}

def break_tie(slugs, code, cur):
    """Pieces of one product got different categories. 1) the piece the product is named after wins (item code 'Dresser'
    matches 'dressers-and-chests', not the mirror); 2) else keep the one category the product already has today."""
    ct = _tokens(code)
    score = {s: len(ct & _tokens(s)) for s in slugs}
    top = max(score.values(), default=0)
    best = [s for s, v in score.items() if v == top and top > 0]
    if len(best) == 1: return best[0], 'tiebreak:item_code'
    pool = best or list(slugs)
    have = [s for s in pool if s in cur]
    if len(have) == 1: return have[0], 'tiebreak:current_link'
    # 3) same branch as the product's current links: 'kids-...' links pick the kids candidate, 'bedroom-...' the bedroom one.
    #    If the current links span both branches (or match none), it stays a conflict for a human.
    branches = {c.split('-')[0] for c in cur}
    same = [s for s in pool if s.split('-')[0] in branches]
    if len(same) == 1: return same[0], 'tiebreak:current_branch'
    return None, ''

def rollup(products, raw_of, decisions, package_rules, current, keep_current_components=False):
    out = []
    for p, code in products.items():
        pieces = raw_of.get(p, [])
        cur = current.get(p, set())
        row = dict(product=p, item_code=code or '', n_raw_items=len(pieces), state='', category='', rule='', current=' | '.join(sorted(cur)))
        if code in package_rules:
            row.update(state='assigned', category=package_rules[code], rule=f'package:{code}')
        elif not pieces:
            row['state'] = 'no_raw_item'
        else:
            ds = [decisions[r] for r in pieces if r in decisions]
            if not ds: row['state'] = 'not_in_run'
            else:
                got = [(slug, rule, slist or [slug]) for outcome, slug, rule, slist in ds if outcome == 'assigned' and slug]
                real = [g for g in got if not g[0].startswith('component-skus')] or got
                slugs = {s for s, _, _ in real}
                component_only = bool(got) and all(g[0].startswith('component-skus') for g in got)
                if keep_current_components and component_only and cur:      # OPT-IN (--keep-current-components): every piece is a Component, so keep the product's current categories
                    row.update(state='keep_current', category=' | '.join(sorted(cur)), rule='keep_current:component_only')     # so it keeps the categories it has today
                elif any(g[1] == 'navigable_categories' or len(g[2]) > 1 for g in got):       # navigable categories, or any decision that holds several categories: a product can be in several, keep ALL
                    every = sorted({s for _, _, sl in real for s in sl})
                    row.update(state='assigned' if len(got) == len(ds) else 'assigned_partial', category=' | '.join(every), rule=next((g[1] for g in got if g[1] == 'navigable_categories'), got[0][1]))
                elif not got: row['state'] = 'review'
                elif len(slugs) > 1:
                    pick, how = break_tie(slugs, code, cur)
                    if pick: row.update(state='assigned', category=pick, rule=how)
                    else: row.update(state='conflict', category=' | '.join(sorted(slugs)))
                else:
                    row.update(state='assigned' if len(got) == len(ds) else 'assigned_partial', category=next(iter(slugs)), rule=real[0][1])
        if row['state'] == 'keep_current': row['vs_current'] = 'kept'
        elif row['category'] and '|' not in row['category']:
            row['vs_current'] = 'already_linked' if row['category'] in cur else ('no_links' if not cur else 'would_add')
        else: row['vs_current'] = ''
        out.append(row)
    return out

def main():
    import cascade as CA
    from dumpreader import rows
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='reports/shadow.db'); ap.add_argument('--dump', default='dump_for_evidence.sql')
    ap.add_argument('--vendor', default='vendors/ashley.yaml'); ap.add_argument('--out', default='reports/product_rollup.csv')
    ap.add_argument('--keep-current-components', action='store_true', help="a product whose pieces are ALL Components keeps its current categories instead of taking the component-skus-* category (off by default: Ashley's navigable categories decide)")
    a = ap.parse_args()
    cfg = CA.K.load_vendor_config(a.vendor)
    products = {p['uuid']: p['item_code'] for p in rows(a.dump, 'pim_products') if not p.get('deleted_at')}
    raw_of = C.defaultdict(list)
    for r in rows(a.dump, 'pim_product_raw_items'): raw_of[r['product_id']].append(r['raw_item_id'])
    import json
    conn = sqlite3.connect(a.db)
    try: dec_rows = conn.execute("select subject_uuid, outcome, primary_slug, rule, slugs from router_decisions where status in ('shadow','applied') order by id").fetchall()
    except sqlite3.OperationalError: dec_rows = [r + (None,) for r in conn.execute("select subject_uuid, outcome, primary_slug, rule from router_decisions where status in ('shadow','applied') order by id")]
    decisions = {u: (o, s, rule, json.loads(sl) if sl else None) for u, o, s, rule, sl in dec_rows}     # slugs = every category of a multi-category decision
    slug = {c['uuid']: c['slug'] for c in rows(a.dump, 'pim_categories')}
    current = C.defaultdict(set)
    for r in rows(a.dump, 'pim_product_categories'):
        if r['category_id'] in slug: current[r['product_id']].add(slug[r['category_id']])
    res = rollup(products, raw_of, decisions, cfg.get('package_rules') or {}, current, a.keep_current_components)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
    n = len(res); st = C.Counter(r['state'] for r in res)
    print(f'{n} products')
    for k, v in st.most_common(): print(f'  {k:16s} {v:6d}  {100*v/n:5.1f}%')
    ok = [r for r in res if r['state'] in ('assigned', 'assigned_partial', 'keep_current')]
    vs = C.Counter(r['vs_current'] for r in ok)
    print(f'\nclassified (assigned + assigned_partial + keep_current): {len(ok)} ({100*len(ok)/n:.1f}%)')
    print('  against the products\' current categories:', dict(vs))
    print('by rule:', dict(C.Counter(r['rule'].split(':')[0] for r in ok).most_common()))
    print(f'wrote {a.out}')

if __name__ == '__main__':
    main()