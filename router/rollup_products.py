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
Follow navcats (optional, --follow-navcats-amp = every AMP master in --amp-map picked by its variants' navcats, no list needed; or --follow-navcats CSV with a master/slug column): for the products listed, where the current categories and the navcats differ, navcats win:
the column to_remove lists the product's current LEAF categories (leaves of the pim_categories tree, parents are never listed) that its picked categories do not contain.
It is a plan only: this script writes nothing to any database, and vs_current / the counts are unchanged by it.
DECIDED 2026-10-29 (component products): (1) a kit Ashley files only under Component SKUs follows its own navcats -> the component-skus-<room> LEAF (rule kit_component_categories);
the 'component-skus' parent is never linked, and no normal leaf is added. (2) The importer strips "Component SKUs", so these products already hold the room parent: that link
is kept, rows are add-only and a kit_component_categories row never carries to_remove. (3) An AMP master takes its variants' navcats (--amp-map, repeatable); an AMP master
with no variant map whose pieces are all Components is sent to review (amp_master_no_variant_map) instead of silently taking component-skus-*.
--pieces-fallback (optional): order becomes approved batch -> package rule -> Ashley's own categories -> the pieces' categories (rule bundle_from_pieces:<rule>) -> uncategorized. Without it a product whose own record lists nothing is uncategorized, as before.
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

def rollup(products, raw_of, decisions, package_rules, current, keep_current_components=False, kit_nav=None, own_nav=None, approved=None, follow=None, leaf=None, follow_rules=None, amp_unmapped=None, amp_default_nav=None, pieces_fallback=False):
    kit_nav = kit_nav or {}
    amp_default_nav = amp_default_nav or {}  # AMP master uuid -> leaves of its own default_variant (only for masters in amp_unmapped)
    amp_unmapped = amp_unmapped or set()     # AMP master uuids with no variant map: their pieces' component rule must not decide for them
    follow = follow or set()     # product uuids whose current LEAF links that the pick does not contain are listed in to_remove (navcats win)
    leaf = leaf or set()
    follow_rules = follow_rules or set()     # when given, only products picked by one of these rules are followed (e.g. kit_navigable_categories)
    approved = approved or {}    # product uuid -> categories of an explicitly approved add-batch (e.g. reports/links_to_add.csv)
    own_nav = own_nav or {}      # product uuid -> its OWN Ashley record: [usable leaf slugs], or None when the record lists no navigable categories      # product uuid -> usable leaf slugs from the kit's own Ashley categories ([] = Ashley answered, but no usable leaf)
    out = []
    for p, code in products.items():
        pieces = raw_of.get(p, [])
        cur = current.get(p, set())
        row = dict(product=p, item_code=code or '', n_raw_items=len(pieces), state='', category='', rule='', current=' | '.join(sorted(cur)))
        if p in approved:                                   # an approved add-batch decides: its categories win over the own record and the pieces
            row.update(state='assigned', category=' | '.join(approved[p]), rule='approved_batch')
        elif code in package_rules and ((p in kit_nav and kit_nav[p] is None) or (p in own_nav and own_nav[p] is None)):
            # DECIDED 2026-10-29: a package whose Ashley record lists nothing ('Uncategorized') follows the package rule: it keeps its set category
            row.update(state='assigned', category=package_rules[code], rule=f'package:{code}')
        elif p in kit_nav and kit_nav[p] is None and not pieces_fallback:           # Ashley's own record answered and lists no navigable categories (or only 'Uncategorized')
            row.update(state='uncategorized', category=UNCATEGORIZED, rule='no_navigable_categories')
        elif p in kit_nav and kit_nav[p] is not None:       # the kit's own categories decide, not its pieces' hidden Component ones
            if kit_nav[p]:      # a kit whose Ashley categories are ONLY component-skus-* gets its own rule name, so batch scripts keyed on kit_navigable_categories never pick it up by accident
                only_comp = all(x.startswith(COMPONENT_PREFIX) for x in kit_nav[p])
                row.update(state='assigned', category=' | '.join(kit_nav[p]), rule='kit_component_categories' if only_comp else 'kit_navigable_categories')
            else: row.update(state='review', rule='kit_no_usable_leaf')
        elif p in own_nav and own_nav[p] is None and not pieces_fallback:           # its own Ashley record lists nothing: UNCATEGORIZED (decided 2026-10-29, replaces the earlier keep-where-it-is rule)
            row.update(state='uncategorized', category=UNCATEGORIZED, rule='own_record_uncategorized')
        elif own_nav.get(p):                                # its own Ashley record lists categories: that is where it goes, not the pieces' union
            row.update(state='assigned', category=' | '.join(own_nav[p]), rule='own_record_categories')
        elif code in package_rules:                         # no fetched Ashley record for this package: the item-code rule stays as the fallback
            row.update(state='assigned', category=package_rules[code], rule=f'package:{code}')
        elif not pieces:
            row['state'] = 'no_raw_item'
        else:
            ds = [decisions[r] for r in pieces if r in decisions]
            if not ds and p in amp_unmapped and amp_default_nav.get(p):      # no router decision for its pieces, no variant map: its own default variant's navcats decide
                row.update(state='assigned', category=' | '.join(amp_default_nav[p]), rule='kit_component_categories' if all(x.startswith(COMPONENT_PREFIX) for x in amp_default_nav[p]) else 'kit_navigable_categories')
            elif not ds: row['state'] = 'not_in_run'
            else:
                got = [(slug, rule, slist or [slug]) for outcome, slug, rule, slist in ds if outcome == 'assigned' and slug]
                real = [g for g in got if not g[0].startswith('component-skus')] or got
                slugs = {s for s, _, _ in real}
                component_only = bool(got) and all(g[0].startswith('component-skus') for g in got)
                if p in amp_unmapped and component_only:                    # AMP master, variants unknown: do not let its Component pieces decide
                    if amp_default_nav.get(p):      # no variant map, but the master's own default variant has navcats: those decide, not the Component pieces
                        row.update(state='assigned', category=' | '.join(amp_default_nav[p]), rule='kit_component_categories' if all(x.startswith(COMPONENT_PREFIX) for x in amp_default_nav[p]) else 'kit_navigable_categories')
                    else: row.update(state='review', rule='amp_master_no_variant_map')
                elif keep_current_components and component_only and cur:      # OPT-IN (--keep-current-components): every piece is a Component, so keep the product's current categories
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
        if pieces_fallback and ((p in kit_nav and kit_nav[p] is None) or (p in own_nav and own_nav[p] is None)) and row['rule'] and row['rule'] != 'approved_batch' \
                and not row['rule'].startswith(('package:', 'kit_', 'own_record_categories')):
            row['rule'] = 'bundle_from_pieces:' + row['rule']     # --pieces-fallback: Ashley's record listed nothing, so the product took its pieces' categories (new label: audit these rows)
        if row['state'] == 'keep_current': row['vs_current'] = 'kept'
        elif row['state'] == 'uncategorized': row['vs_current'] = 'already_uncategorized' if cur == {UNCATEGORIZED} else 'to_uncategorize'   # changes its links, so not an add-only row
        elif row['category'] and row['state'] != 'conflict':    # one or several categories, compared as a set: already linked only when ALL are
            row['vs_current'] = 'already_linked' if set(row['category'].split(' | ')) <= cur else ('no_links' if not cur else 'would_add')
        else: row['vs_current'] = ''
        row['to_remove'] = ''
        if p in follow and row['state'] == 'assigned' and row['category'] and row['rule'] != 'kit_component_categories' and (not follow_rules or row['rule'] in follow_rules):      # navcats win: current leaf links the pick does not have (parents are never listed)
            pick = set(row['category'].split(' | '))
            row['to_remove'] = ' | '.join(sorted(c for c in cur if c in leaf and c not in pick))
        out.append(row)
    return out

def build_kit_nav(dump, res, navcats_csv, amp_map_csv=None, amp_mode='union', amp_navcats=None):
    """{product uuid: [usable leaf slugs]} for kit products. navcats_csv = fetch_navcats.py output (rows with status ok only count)."""
    import cascade as CA
    from dumpreader import rows
    codes = {}
    for f in ([navcats_csv] if isinstance(navcats_csv, str) else navcats_csv):     # --kit-navcats is repeatable; a later file only fills SKUs the earlier ones lack
        for k, v in CA.load_navcats(f).items(): codes.setdefault(k, v)       # sku -> codes; failed fetches are left out (unknown, not 'none')
    var_codes = dict(codes)       # variant SKU lookups: the kit navcats first, --amp-navcats only fill SKUs they lack (so a product slug in them never becomes a kit entry)
    for f in ([amp_navcats] if isinstance(amp_navcats, str) else (amp_navcats or [])):
        for k, v in CA.load_navcats(f).items(): var_codes.setdefault(k, v)
    amp = C.OrderedDict()
    for f in ([amp_map_csv] if isinstance(amp_map_csv, str) else (amp_map_csv or [])):
        for r in CA._csv_any(f):          # master_id|product_slug, sku|default_variant_sku, default_variant|default_variant_sku
            m = r.get('master_id') or r.get('product_slug') or ''
            sku = r.get('sku') or r.get('default_variant_sku') or ''
            if not m.startswith('AMP') or not sku: continue          # e.g. kit rows of an audit export have no master
            pair = (sku, r.get('default_variant') or r.get('default_variant_sku') or '')
            if pair not in amp.setdefault(m, []): amp[m].append(pair)
    out = {}
    for p in rows(dump, 'pim_products'):
        if p.get('deleted_at'): continue
        slug = p['slug']
        if slug in codes: out[p['uuid']] = kit_slugs(codes[slug], res) if codes[slug] else None   # [] = Ashley answered and listed nothing -> None = uncategorized
        elif slug in amp:
            variants = sorted(amp[slug], key=lambda v: v[0] != v[1])      # default variant first, so its category leads
            ok = [(sku, var_codes[sku]) for sku, _ in variants if sku in var_codes]
            if amp_mode == 'default' and ok and ok[0][0] == variants[0][1]: ok = ok[:1]
            if ok and not any(c for _, c in ok): out[p['uuid']] = None                 # every variant answered and listed nothing
            elif ok:
                leaves = list(dict.fromkeys(s for _, c in ok for s in CA.nav_slugs(c, res)))
                out[p['uuid']] = leaves or list(dict.fromkeys(s for _, c in ok for s in kit_slugs(c, res)))
    return out

def build_amp_default_nav(dump, res, navcats_csv, have, amp_navcats=None):
    """{master uuid: [usable leaf slugs]} for AMP masters with no variant map (not in `have`): the master's OWN default_variant (pim_products) looked up in navcats.
    Used only where the guard would otherwise send an all-Component master to review (amp_master_no_variant_map)."""
    import cascade as CA
    from dumpreader import rows
    codes = {}
    for f in ([navcats_csv] if isinstance(navcats_csv, str) else navcats_csv) + ([amp_navcats] if isinstance(amp_navcats, str) else list(amp_navcats or [])):
        for k, v in CA.load_navcats(f).items(): codes.setdefault(k, v)
    out = {}
    for p in rows(dump, 'pim_products'):
        dv = p.get('default_variant')
        if p.get('deleted_at') or not p['slug'].startswith('AMP') or p['uuid'] in have or not dv or dv not in codes or not codes[dv]: continue
        leaves = CA.nav_slugs(codes[dv], res) or kit_slugs(codes[dv], res)
        if leaves: out[p['uuid']] = leaves
    return out

def build_own_nav(dump, res, own_csv):
    """{product uuid: [leaf slugs] | None} from the products' OWN Ashley records (pim_vendor_api_ingestion export: sku, navigableCategories, status).
    None = the record answered and lists nothing. A record with only unusable (e.g. Component SKUs) categories is left out: not decided here."""
    import cascade as CA
    from dumpreader import rows
    try: csv.field_size_limit(2**31 - 1)      # sys.maxsize overflows on Windows
    except OverflowError: csv.field_size_limit(2**30)
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

PROFILES = {      # `python rollup_products.py --profile onebuild` = the whole onebuild catalog from ONE navcats file, ONE output
    'onebuild': dict(dump='onebuilddemo_for_router.sql', db='reports/shadow_fresh.db', navcats='onebuild/navcats.csv',
                     amp_map=['onebuild/amp_map.csv'], approved_links='onebuild/approved_links.csv', follow_navcats_amp=True,
                     out='reports/product_rollup_onebuild.csv', component_links_out='', kit_links_out='', remove_links_out='', uncategorize_out=''),
}

def main():
    import cascade as CA
    from dumpreader import rows
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', choices=sorted(PROFILES), help='a whole run in one flag (see PROFILES); any other flag still overrides it')
    ap.add_argument('--navcats', help='ONE navcats file per database (fetch_navcats.py output: sku, navigableCategories, status). Every record is used the same way: a product takes its own record, an AMP master takes its variants\' records. Replaces --kit-navcats / --amp-navcats / --own-records')
    ap.add_argument('--db', default='reports/shadow.db'); ap.add_argument('--dump', default='dump_for_evidence.sql')
    ap.add_argument('--vendor', default='vendors/ashley.yaml'); ap.add_argument('--out', default='reports/product_rollup.csv')
    ap.add_argument('--keep-current-components', action='store_true', help="a product whose pieces are ALL Components keeps its current categories instead of taking the component-skus-* category (off by default: Ashley's navigable categories decide)")
    ap.add_argument('--kit-navcats', action='append', help='fetch_navcats.py output for the kit products (keyed by product slug): kits take their own Ashley categories. Repeatable: the files are merged')
    ap.add_argument('--amp-navcats', action='append', help='extra navcats CSV used ONLY to look up the variant SKUs of AMP masters (--amp-map / default_variant); fills SKUs --kit-navcats lacks, never keys a product by its own slug')
    ap.add_argument('--amp-map', action='append', help='CSV master_id,sku,default_variant: AMP masters take the categories of their variant SKUs (looked up in --kit-navcats)')
    ap.add_argument('--amp-mode', choices=['union', 'default'], default='union', help='union = every variant\'s categories, default variant first; default = the default variant only')
    ap.add_argument('--approved-links', help='CSV product,category_slug (e.g. reports/links_to_add.csv): products in an approved add-batch take those categories (rule approved_batch)')
    ap.add_argument('--own-records', help='export of the products\' own Ashley records (sku, navigableCategories, status): own categories decide; a record listing none keeps the product where it is')
    ap.add_argument('--follow-navcats-amp', action='store_true', help="same as --follow-navcats but without a list: every AMP master in --amp-map whose pick comes from its variants' navcats (rule kit_navigable_categories) follows navcats. Works on any DB that has the maps")
    ap.add_argument('--component-links-out', default='reports/links_to_add_components.csv', help='dry-run links file for the kit_component_categories rows that would add a component-skus-* leaf (nothing is written to any database)')
    ap.add_argument('--kit-links-out', default='reports/links_to_add_kits.csv', help='dry-run links file: the kit_navigable_categories rows that would add leaves (same columns as apply_kit_would_add.py)')
    ap.add_argument('--remove-links-out', default='reports/links_to_remove.csv', help='dry-run file: the leaf links navcats say to drop (to_remove, --follow-navcats / --follow-navcats-amp products only)')
    ap.add_argument('--sql-out', default=None, help='OPT-IN, off by default: MySQL script that applies every would_add link and every to_remove link to pim_product_categories (one transaction). NOT run by this script')
    ap.add_argument('--uncategorize-out', default='reports/links_to_uncategorize.csv', help='dry-run file: products whose Ashley record lists no categories, with the uncategorized link to add and the current links to drop')
    ap.add_argument('--pieces-fallback', action='store_true', help="a product whose own Ashley record lists no navigable categories ('Uncategorized', e.g. a Room Bundle or an X2/X4 pair) and that no approved batch or package rule covers takes the categories of its PIECES instead of becoming uncategorized (rule bundle_from_pieces:<piece rule>). Uncategorized stays only when the pieces give nothing")
    ap.add_argument('--follow-navcats', help="CSV with a master (or product_slug / slug) column, e.g. the 66 AMP default-variant audit: for those products navcats win where they differ from the current categories; the current leaf links the pick does not contain are listed in to_remove (plan only)")
    pre, _ = ap.parse_known_args()
    if pre.profile: ap.set_defaults(**PROFILES[pre.profile])
    a = ap.parse_args()
    if a.navcats: a.kit_navcats, a.amp_navcats, a.own_records = [a.navcats], None, None
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
    resrc = CA.resources_from_dump(cfg, a.dump) if (a.kit_navcats or a.own_records or a.follow_navcats or a.follow_navcats_amp) else None
    kit_nav = build_kit_nav(a.dump, resrc, a.kit_navcats, a.amp_map, a.amp_mode, a.amp_navcats) if a.kit_navcats else None
    own_nav = build_own_nav(a.dump, resrc, a.own_records) if a.own_records else None
    slug_of = {p['uuid']: p['slug'] for p in rows(a.dump, 'pim_products')}
    follow, follow_missing = set(), []
    if a.follow_navcats_amp:
        if not a.amp_map: sys.exit('--follow-navcats-amp needs --amp-map')
        uuid_of = {sl: u for u, sl in slug_of.items()}
        for f in a.amp_map:
            for r in CA._csv_any(f):
                m = r.get('master_id') or r.get('product_slug') or ''
                if m in uuid_of: follow.add(uuid_of[m])
    if a.follow_navcats:
        uuid_of = {sl: u for u, sl in slug_of.items()}
        for r in csv.DictReader(open(a.follow_navcats, encoding='utf-8-sig', newline='')):
            key = (r.get('master') or r.get('product_slug') or r.get('slug') or '').strip()
            if key in uuid_of: follow.add(uuid_of[key])
            elif key: follow_missing.append(key)
    approved = C.defaultdict(list)
    if a.approved_links:
        for r in csv.DictReader(open(a.approved_links, encoding='utf-8-sig', newline='')): approved[r['product']].append(r['category_slug'])
    amp_default_nav = build_amp_default_nav(a.dump, resrc, a.kit_navcats, set(kit_nav or {}), a.amp_navcats) if a.kit_navcats else {}
    amp_unmapped = {u for u, sl in slug_of.items() if sl.startswith('AMP') and u in products and not (kit_nav and u in kit_nav)}
    res = rollup(products, raw_of, decisions, cfg.get('package_rules') or {}, current, a.keep_current_components, kit_nav, own_nav, dict(approved), follow, resrc.leaf if resrc else None, {'kit_navigable_categories'} if (a.follow_navcats_amp and not a.follow_navcats) else None, amp_unmapped, amp_default_nav, pieces_fallback=a.pieces_fallback)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    res = [dict(slug=slug_of.get(r['product'], ''), **r) for r in res]       # slug first, as in the committed product_rollup_final.csv
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
    if a.follow_navcats or a.follow_navcats_amp:
        fol = [r for r in res if r['product'] in follow]; rem = [r for r in fol if r['to_remove']]
        print(f'follow navcats ({a.follow_navcats or "AMP masters in --amp-map, rule kit_navigable_categories"}): {len(follow)} products found in the dump, {len(follow_missing)} not found', ('-> ' + ', '.join(follow_missing[:10])) if follow_missing else '')
        print('  their rules:', dict(C.Counter(r['rule'].split(':')[0] or r['state'] for r in fol).most_common()), '| vs_current:', dict(C.Counter(r['vs_current'] for r in fol)))
        print(f'  to_remove (plan only, nothing is written): {sum(len(r["to_remove"].split(" | ")) for r in rem)} leaf links on {len(rem)} products')
        print('  by category:', dict(C.Counter(c for r in rem for c in r['to_remove'].split(' | ')).most_common()))
    comp = [(r['product'], sl, r['item_code'], r['current']) for r in res if r['rule'] == 'kit_component_categories' and r['vs_current'] == 'would_add'
            for sl in (c.strip() for c in r['category'].split('|')) if sl.startswith('component-skus-') and sl not in {c.strip() for c in r['current'].split('|')}]      # add-only, component leaf only
    if a.component_links_out:
        os.makedirs(os.path.dirname(a.component_links_out) or '.', exist_ok=True)
        with open(a.component_links_out, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f); w.writerow(['product', 'category_slug', 'item_code', 'current_categories']); w.writerows(comp)
        print(f'component links to add (dry run, no database touched): {len(comp)} on {len({x[0] for x in comp})} products', dict(C.Counter(x[1] for x in comp).most_common()), '->', a.component_links_out)
    sp = lambda x: [c.strip() for c in x.split('|') if c.strip()]
    unc = [(r['product'], r['slug'], r['item_code'], r['rule'], UNCATEGORIZED, ' | '.join(c for c in sp(r['current']) if c != UNCATEGORIZED)) for r in res if r['vs_current'] == 'to_uncategorize']
    if a.uncategorize_out:
        with open(a.uncategorize_out, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f); w.writerow(['product', 'slug', 'item_code', 'rule', 'category_to_add', 'categories_to_remove']); w.writerows(unc)
        print(f'to uncategorize (dry run): {len(unc)} products -> {a.uncategorize_out}')
    else: print(f'to uncategorize: {len(unc)} products (see vs_current = to_uncategorize in {a.out})')
    kit = [(r['product'], sl, r['item_code'], r['current']) for r in res if r['rule'] == 'kit_navigable_categories' and r['vs_current'] == 'would_add' for sl in sp(r['category']) if sl not in set(sp(r['current']))]
    rem = [(r['product'], sl, r['item_code'], r['category'], r['current']) for r in res if r['to_remove'] for sl in sp(r['to_remove'])]
    for path, head, data in ((a.kit_links_out, ['product', 'category_slug', 'item_code', 'current_categories'], kit), (a.remove_links_out, ['product', 'category_slug_to_remove', 'item_code', 'new_categories', 'current_categories'], rem)):
        if not path: continue
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='') as f: w = csv.writer(f); w.writerow(head); w.writerows(data)
    print(f'kit links to add (dry run): {len(kit)} on {len({x[0] for x in kit})} products -> {a.kit_links_out or "(not written)"}')
    print(f'links to remove (dry run): {len(rem)} on {len({x[0] for x in rem})} products -> {a.remove_links_out or "(not written)"}')
    add_all = [(r['product'], sl) for r in res if r['state'] in ('assigned', 'assigned_partial') and r['vs_current'] == 'would_add' for sl in sp(r['category']) if sl not in set(sp(r['current']))]
    if a.sql_out:
      q = lambda x: x.replace('\\', '\\\\').replace("'", "''")
      os.makedirs(os.path.dirname(a.sql_out) or '.', exist_ok=True)
      with open(a.sql_out, 'w', encoding='utf-8', newline='\n') as f:
          f.write(f'-- generated by rollup_products.py from {a.out}: {len(add_all)} links to add, {len(rem)} links to remove. Review, then run it once on the DB that holds pim_product_categories.\n')
          f.write('-- INSERT IGNORE: a link that already exists is skipped. A slug missing from pim_categories inserts nothing, so expect 333 new rows (fewer only if a link already exists).\nSTART TRANSACTION;\n')
          for p, sl in add_all: f.write(f"INSERT IGNORE INTO pim_product_categories (product_id, category_id, created_at, updated_at) SELECT '{q(p)}', c.uuid, NOW(), NOW() FROM pim_categories c WHERE c.slug = '{q(sl)}';\n")
          for p, sl, *_ in rem: f.write(f"DELETE pc FROM pim_product_categories pc JOIN pim_categories c ON c.uuid = pc.category_id WHERE pc.product_id = '{q(p)}' AND c.slug = '{q(sl)}';\n")
          f.write('COMMIT;\n')
      print(f'apply script (NOT run): {len(add_all)} inserts + {len(rem)} deletes -> {a.sql_out}')
    print(f'wrote {a.out}')

if __name__ == '__main__':
    main()