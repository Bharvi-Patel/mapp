"""Roll the raw-item decisions up to PRODUCTS (the unit that has category links on the site). Run from the router folder
after a shadow run:
    python rollup_products.py [--db reports/shadow.db] [--dump dump_for_evidence.sql]
Per product:
  - item_code in package_rules (Bedroom Package, Dining Package ...)  -> its set category (package rule, same as the router's)
  - otherwise the decisions of its raw items. Component pieces (component-skus-*) are set aside when the product has a
    real category from another piece; if all assigned pieces agree the product takes that category.
States: assigned | assigned_partial (some pieces still in review) | keep_current (only with --keep-current-components: every piece is a Component, so the product keeps
        the categories it has today; off by default, because Ashley's navigable categories for those pieces ARE the component categories) | conflict (pieces disagree) | review | no_raw_item | not_in_run
Kits (optional, --kit-navcats): a kit product is the sellable item, so it takes ITS OWN Ashley navigableCategories (fetch_navcats.py output keyed by the
product slug) instead of the categories rolled up from its Component pieces. AMP products are masters of variant SKUs (--amp-map, from
pim_product_masters + pim_product_variation_masters); they take the categories of their variants (--amp-mode union = every variant's, default variant first;
default = the default variant only). A kit whose fetch failed is left to the old logic. A kit Ashley files only under parents has no usable leaf -> review.
Writes reports/product_rollup.csv and prints counts, plus how often the pick is already one of the product's current categories."""
import argparse, collections as C, csv, os, re, sqlite3, sys

COMPONENT_PREFIX = 'component-skus-'
UNCATEGORIZED = 'uncategorized'      # the store's own category for a product Ashley gives no navigable categories

def kit_slugs(codes, res):
    """Usable categories of a kit from its own Ashley codes. The router's normal filter (CA.nav_slugs) drops excluded slugs, and the config excludes every
    component-skus-* leaf. A kit Ashley files ONLY under those has nothing left, so for such a kit (and only then) the component-skus-* leaves are allowed:
    Ashley's navigable category is where the product goes. Other excluded slugs (uncategorized, store-displays) stay excluded."""
    import cascade as CA
    usual = CA.nav_slugs(codes, res)
    if usual: return usual
    prefix = (res.cfg.get('component_rule') or {}).get('slug_prefix', COMPONENT_PREFIX)
    out = [res.vendor_map.get(c) or res.code_slug.get(c, c) for c in (codes or [])]
    return [x for x in dict.fromkeys(out) if x.startswith(prefix) and x in res.leaf and x in res.store and x not in res.inactive]

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

def rollup(products, raw_of, decisions, package_rules, current, keep_current_components=False, kit_nav=None, own_nav=None):
    kit_nav = kit_nav or {}
    own_nav = own_nav or {}      # product uuid -> its OWN Ashley record: [usable leaf slugs], or None when the record lists no navigable categories      # product uuid -> usable leaf slugs from the kit's own Ashley categories ([] = Ashley answered, but no usable leaf)
    out = []
    for p, code in products.items():
        pieces = raw_of.get(p, [])
        cur = current.get(p, set())
        row = dict(product=p, item_code=code or '', n_raw_items=len(pieces), state='', category='', rule='', current=' | '.join(sorted(cur)))
        if p in kit_nav and kit_nav[p] is None:           # Ashley's own record answered and lists no navigable categories (or only 'Uncategorized')
            row.update(state='uncategorized', category=UNCATEGORIZED, rule='no_navigable_categories')
        elif p in kit_nav:                                  # the kit's own categories decide, not its pieces' hidden Component ones
            if kit_nav[p]:      # a kit whose Ashley categories are ONLY component-skus-* gets its own rule name, so batch scripts keyed on kit_navigable_categories never pick it up by accident
                only_comp = all(x.startswith(COMPONENT_PREFIX) for x in kit_nav[p])
                row.update(state='assigned', category=' | '.join(kit_nav[p]), rule='kit_component_categories' if only_comp else 'kit_navigable_categories')
            else: row.update(state='review', rule='kit_no_usable_leaf')
        elif p in own_nav and own_nav[p] is None:           # its own Ashley record lists nothing: keep it where it is today (decided), do not add its pieces' categories
            row.update(state='keep_current', category=' | '.join(sorted(cur)), rule='own_record_uncategorized_keep_current')
        elif own_nav.get(p):                                # its own Ashley record lists categories: that is where it goes, not the pieces' union
            row.update(state='assigned', category=' | '.join(own_nav[p]), rule='own_record_categories')
        elif code in package_rules:                         # no fetched Ashley record for this package: the item-code rule stays as the fallback
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
        elif row['state'] == 'uncategorized': row['vs_current'] = 'already_uncategorized' if cur == {UNCATEGORIZED} else 'to_uncategorize'   # changes its links, so not an add-only row
        elif row['category'] and row['state'] != 'conflict':    # one or several categories, compared as a set: already linked only when ALL are
            row['vs_current'] = 'already_linked' if set(row['category'].split(' | ')) <= cur else ('no_links' if not cur else 'would_add')
        else: row['vs_current'] = ''
        out.append(row)
    return out

def build_kit_nav(dump, res, navcats_csv, amp_map_csv=None, amp_mode='union'):
    """{product uuid: [usable leaf slugs]} for kit products. navcats_csv = fetch_navcats.py output (rows with status ok only count)."""
    import cascade as CA
    from dumpreader import rows
    codes = CA.load_navcats(navcats_csv)                     # sku -> codes; failed fetches are left out (unknown, not 'none')
    amp = C.OrderedDict()
    if amp_map_csv:
        for r in CA._csv_any(amp_map_csv): amp.setdefault(r['master_id'], []).append((r['sku'], r.get('default_variant') or ''))
    out = {}
    for p in rows(dump, 'pim_products'):
        if p.get('deleted_at'): continue
        slug = p['slug']
        if slug in codes: out[p['uuid']] = kit_slugs(codes[slug], res) if codes[slug] else None   # [] = Ashley answered and listed nothing -> None = uncategorized
        elif slug in amp:
            variants = sorted(amp[slug], key=lambda v: v[0] != v[1])      # default variant first, so its category leads
            ok = [(sku, codes[sku]) for sku, _ in variants if sku in codes]
            if amp_mode == 'default' and ok and ok[0][0] == variants[0][1]: ok = ok[:1]
            if ok and not any(c for _, c in ok): out[p['uuid']] = None                 # every variant answered and listed nothing
            elif ok:
                leaves = list(dict.fromkeys(s for _, c in ok for s in CA.nav_slugs(c, res)))
                out[p['uuid']] = leaves or list(dict.fromkeys(s for _, c in ok for s in kit_slugs(c, res)))
    return out

def build_own_nav(dump, res, own_csv):
    """{product uuid: [leaf slugs] | None} from the products' OWN Ashley records (pim_vendor_api_ingestion export: sku, navigableCategories, status).
    None = the record answered and lists nothing. A record with only unusable (e.g. Component SKUs) categories is left out: not decided here."""
    import cascade as CA
    from dumpreader import rows
    csv.field_size_limit(sys.maxsize)
    recs = {}
    for r in CA._csv_any(own_csv):
        if (r.get('status') or 'ok').strip() == 'ok': recs.setdefault(r['sku'], r.get('navigableCategories'))
    out = {}
    for p in rows(dump, 'pim_products'):
        if p.get('deleted_at') or p['slug'] not in recs: continue
        codes = CA.nav_codes(recs[p['slug']])
        if not codes: out[p['uuid']] = None
        else:
            sl = CA.nav_slugs(codes, res)
            if sl: out[p['uuid']] = sl
    return out

def main():
    import cascade as CA
    from dumpreader import rows
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='reports/shadow.db'); ap.add_argument('--dump', default='dump_for_evidence.sql')
    ap.add_argument('--vendor', default='vendors/ashley.yaml'); ap.add_argument('--out', default='reports/product_rollup.csv')
    ap.add_argument('--keep-current-components', action='store_true', help="a product whose pieces are ALL Components keeps its current categories instead of taking the component-skus-* category (off by default: Ashley's navigable categories decide)")
    ap.add_argument('--kit-navcats', help='fetch_navcats.py output for the kit products (keyed by product slug): kits take their own Ashley categories')
    ap.add_argument('--amp-map', help='CSV master_id,sku,default_variant: AMP masters take the categories of their variant SKUs (looked up in --kit-navcats)')
    ap.add_argument('--amp-mode', choices=['union', 'default'], default='union', help='union = every variant\'s categories, default variant first; default = the default variant only')
    ap.add_argument('--own-records', help='export of the products\' own Ashley records (sku, navigableCategories, status): own categories decide; a record listing none keeps the product where it is')
    a = ap.parse_args()
    cfg = CA.K.load_vendor_config(a.vendor)
    products = {p['uuid']: p['item_code'] for p in rows(a.dump, 'pim_products') if not p.get('deleted_at')}
    raw_of = C.defaultdict(list)
    for r in rows(a.dump, 'pim_product_raw_items'): raw_of[r['product_id']].append(r['raw_item_id'])
    import json
    import dbconn
    conn, ph = dbconn.connect(a.db)
    try: dec_rows = dbconn.fetch(conn, ph, "select subject_uuid, outcome, primary_slug, rule, slugs from router_decisions where status in ('shadow','applied') order by id")
    except Exception:       # older table without the slugs column
        try: conn.rollback()
        except Exception: pass
        dec_rows = [tuple(r) + (None,) for r in dbconn.fetch(conn, ph, "select subject_uuid, outcome, primary_slug, rule from router_decisions where status in ('shadow','applied') order by id")]
    decisions = {u: (o, s, rule, json.loads(sl) if sl else None) for u, o, s, rule, sl in dec_rows}     # slugs = every category of a multi-category decision
    slug = {c['uuid']: c['slug'] for c in rows(a.dump, 'pim_categories')}
    current = C.defaultdict(set)
    for r in rows(a.dump, 'pim_product_categories'):
        if r['category_id'] in slug: current[r['product_id']].add(slug[r['category_id']])
    kit_nav = build_kit_nav(a.dump, CA.resources_from_dump(cfg, a.dump), a.kit_navcats, a.amp_map, a.amp_mode) if a.kit_navcats else None
    own_nav = build_own_nav(a.dump, CA.resources_from_dump(cfg, a.dump), a.own_records) if a.own_records else None
    res = rollup(products, raw_of, decisions, cfg.get('package_rules') or {}, current, a.keep_current_components, kit_nav, own_nav)
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
    print('uncategorized (Ashley lists no navigable categories):', st.get('uncategorized', 0))
    print(f'wrote {a.out}')

if __name__ == '__main__':
    main()