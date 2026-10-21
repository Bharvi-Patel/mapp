#!/usr/bin/env python3
"""Cascade: route one product to one category, cheapest step first (Phase 4).

  0 reuse          same vendor + SKU + content hash decided before
  1 human          a person already decided this item
  1a golden_map    SKU is in golden.jsonl (optional, shadow --golden-map): its first accepted slug that the store can take
  2 sku_prefix     vendor config, e.g. StoreDisplay (100-) -> store-displays
  2a navigable     (needs trust_vendor_path) the vendor's own navigableCategories, when we have them: ALL usable leaves (a product can be in several);
                   none given -> outcome 'uncategorized' (flag, no slug). Unknown (fetch failed) -> carry on below.
  3 package        product item_code -> set category (vendor config)
  4 review_class   item classes that never get a category yet -> review
  5 vendor_map     reviewed Ashley-category -> our-category map          (needs trust_vendor_path)
  6 vendor_path    the item's vendor path names exactly one leaf         (needs trust_vendor_path)
  7 narrow         options = path leaves, else the item class's pool
  8 model          a classifier picks ONE option or none; code applies the threshold
Anything not confidently decided goes to review with a shortlist. Every output passes validate_output.

  python cascade.py eval [--dump FILE] [--trust-vendor-path] [--unreviewed-map]   score the rules on the answer key"""
import argparse, csv, json, os, re, sys
import collections as C
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'contract'))
import contract as K
from contract import RouterInput, RouterOutput

NONE_OF_THESE = '__none_of_these__'
MODEL_CAP = 0.95            # a model never outranks a rule
RULE_CONF = {'golden_map': 0.97, 'reuse': 1.0, 'human': 1.0, 'sku_prefix': 1.0, 'package': 0.99, 'vendor_map': 0.98, 'vendor_path': 0.95, 'item_class': 0.96, 'name_rule': 0.95, 'navigable_categories': 0.98}

def nav_code(path):
    """One Ashley navigableCategories entry -> the ashley_category code stored in pim_vendor_categories.
    'Bedroom - Bedroom Furniture - Beds' -> 'BEDROOMBEDROOMFURNITUREBEDS'. Rule: uppercase, drop whitespace and hyphens;
    other punctuation is kept ('Indoor/Outdoor Rugs' keeps its slash). Checked against all 188 stored codes."""
    return re.sub(r'[\s-]+', '', (path or '').upper())

def nav_codes(nav):
    """navigableCategories (list of cumulative path strings) -> codes, deepest first, no duplicates.
    'Uncategorized' means the vendor gave no category and is dropped."""
    if isinstance(nav, str):
        try: nav = json.loads(nav)
        except ValueError: nav = [nav]
    codes = [nav_code(p) for p in (nav or []) if isinstance(p, str) and p.strip()]
    codes = [c for c in dict.fromkeys(codes) if c and c != 'UNCATEGORIZED']
    return sorted(codes, key=len, reverse=True)

def load_navcats(path):
    """CSV with columns sku, navigableCategories (JSON list), status -> {sku: [codes]}.
    A row whose fetch failed (status bad_body / no_field / not_found / error:*) is left OUT: we do not know its categories,
    which is not the same as the vendor giving none. [] therefore means the API answered and listed nothing (or only 'Uncategorized')."""
    return {r['sku']: nav_codes(r.get('navigableCategories')) for r in _csv_any(path)
            if r.get('sku') and (r.get('status') or 'ok').strip() == 'ok'}

def nav_slugs(codes, res):
    """Navigable-category codes -> our category slugs: every one that is a leaf, in the store, active and not excluded. Order kept (deepest first)."""
    out = [res.vendor_map.get(c) or res.code_slug.get(c, c) for c in (codes or [])]
    return [s for s in dict.fromkeys(out) if s in res.leaf and s in res.store and s not in res.excluded and s not in res.inactive]

class MemoryStore:
    """Decision store used for tests and evaluation. Phase 6 swaps in the router_decisions tables."""
    def __init__(self): self.reuse, self.human = {}, {}
    def find_reuse(self, vendor, sku, chash): return self.reuse.get((vendor, sku, chash))
    def find_human(self, vendor, subject_type, uuid): return self.human.get((vendor, subject_type, uuid))

@dataclass
class Resources:
    cfg: dict
    leaf: set; store: set; inactive: set; excluded: set
    pools: dict = field(default_factory=dict)        # item_class -> [slug, ...] best first (leaf, in store, not excluded)
    vendor_map: dict = field(default_factory=dict)   # vendor category code -> slug (accepted rows only)
    decisions: object = None
    code_slug: dict = field(default_factory=dict)    # vendor category code -> slug, every matched LEAF row (lets step 6 read real codes)
    item_class_map: dict = field(default_factory=dict)   # item_class -> slug, classes Ashley always files in one category (build_item_class_map.py)
    labels: dict = field(default_factory=dict)           # slug -> category name (from the vendor map); Jev reads these as option descriptions
    golden: dict = field(default_factory=dict)           # sku -> [accepted slugs], from golden.jsonl (shadow --golden-map); empty = step off

def threshold_for(cfg, n_options):
    t = cfg['settings'].get('thresholds')
    if not t: return None
    for bound in sorted(int(k) for k in t):
        if n_options <= bound: return t[bound] if bound in t else t[str(bound)]
    return None

def options_for(inp, res, trust):
    """(options, why): the short list the model may choose from."""
    cands = []
    if trust:
        cands = [s for s in dict.fromkeys(res.code_slug.get(c, c) for c in (inp.vendor_category_path or []))
                 if s in res.leaf and s in res.store and s not in res.excluded]
        if len(cands) >= 2: return cands, 'vendor_path'
    pool = res.pools.get((inp.item_class or '').strip())
    return (pool or []), ('class_pool' if pool else 'none')

def usable_leaves(inp, res):
    """The vendor-path categories the router may assign: leaf, in the store, not excluded. Order = path order (deepest path first)."""
    slugs = dict.fromkeys(res.code_slug.get(c, c) for c in (inp.vendor_category_path or []))
    return [x for x in slugs if x in res.leaf and x in res.store and x not in res.excluded]

_STOP = {'and', 'by', 'the', 'of', 'a', 'type', 'size', 'set', 'sets'}
def _words(text):
    return {w[:-1] if len(w) > 3 and w.endswith('s') else w
            for w in re.findall(r'[a-z]+', (text or '').lower()) if w not in _STOP}

def pick_by_name(name, leaves):
    """Tie-break among several vendor-path leaves: the leaf whose own words (those not shared by every
    candidate) appear most in the product name wins. Fewer unmatched leaf words breaks a tie.
    Returns None when there is no clear winner (the row then stays undecided)."""
    if len(leaves) < 2: return None
    lw = {s: _words(s.replace('-', ' ')) for s in leaves}
    shared = set.intersection(*lw.values())
    nw = _words(name)
    scored = []
    for s in leaves:
        own = lw[s] - shared
        scored.append(((len(own & nw), -len(own - nw)), s))
    scored.sort(reverse=True)
    if scored[0][0][0] < 1 or scored[0][0] == scored[1][0]: return None
    return scored[0][1]

def undecided_why(inp, res):
    """Why the vendor-path rules had no answer for this item (diagnostic only; the cascade does not use it)."""
    slugs = list(dict.fromkeys(res.code_slug.get(c, c) for c in (inp.vendor_category_path or [])))
    if not slugs: return 'no_vendor_path'
    leaves = [x for x in slugs if x in res.leaf]
    if not leaves: return 'path_has_no_leaf'
    if all(x in res.excluded for x in leaves): return 'component_or_excluded_only'
    usable = [x for x in leaves if x in res.store and x not in res.excluded]
    if len(usable) >= 2: return 'several_leaves'
    if not usable: return 'leaf_not_in_store'
    return 'one_leaf_but_not_assigned'

def route(inp: RouterInput, res: Resources, model=None, trust_vendor_path=None) -> RouterOutput:
    cfg = res.cfg; ver = str(cfg['version']); chash = K.content_hash(inp)
    trust = cfg['settings'].get('trust_vendor_path') if trust_vendor_path is None else trust_vendor_path
    ds = res.decisions

    def review(reason, cands=None, stage='review', rule=''):
        return RouterOutput('review', None, stage, rule, None, ver, chash, reason, cands)

    def assign(slug, stage, rule, conf, options, exempt=(), cands=None):
        out = RouterOutput('assigned', slug, stage, rule, conf, ver, chash, None, cands)
        ex = set(exempt)                     # slugs named by the reviewed vendor config are trusted, but must exist in the store
        errs = K.validate_output(out, allowed_slugs=set(options) | ex, leaf_slugs=res.leaf | ex,
                                 inactive_slugs=res.inactive - ex, excluded_slugs=res.excluded - ex, store_slugs=res.store)
        return review(errs[0], cands, stage=stage, rule=rule) if errs else out

    def assign_many(slugs, stage, rule, conf, options):
        """Several categories for one product; every one passes the same checks as a single pick."""
        for s in slugs:
            errs = K.validate_output(RouterOutput('assigned', s, stage, rule, conf, ver, chash), allowed_slugs=set(options), leaf_slugs=res.leaf,
                                     inactive_slugs=res.inactive, excluded_slugs=res.excluded, store_slugs=res.store)
            if errs: return review(errs[0], None, stage=stage, rule=rule)
        return RouterOutput('assigned', slugs[0], stage, rule, conf, ver, chash, None, None, slugs=list(slugs))

    if ds:                                                                   # 0, 1
        r = ds.find_reuse(inp.vendor_id, inp.sku, chash)
        if r and len(r) > 2 and r[2] and len(r[2]) > 1: return assign_many(r[2], 'reuse', 'reuse', r[1], res.leaf)
        if r: return assign(r[0], 'reuse', 'reuse', r[1], res.leaf)
        h = ds.find_human(inp.vendor_id, inp.subject_type, inp.subject_uuid)
        if h: return assign(h, 'human', 'prior_human_decision', 1.0, res.leaf)
    gm = res.golden.get(inp.sku)                                             # 1a: SKU is in the golden mapping (only when shadow --golden-map is given)
    if gm:
        slug = next((a for a in gm if a in res.leaf and a in res.store and a not in res.excluded and a not in res.inactive), gm[0])   # first accepted slug the store can take
        return assign(slug, 'rule', 'golden_map', RULE_CONF['golden_map'], res.leaf)       # no valid one -> validate_output sends it to review
    for prefix, slug in (cfg.get('sku_prefix_rules') or {}).items():       # 2
        if (inp.sku or '').startswith(prefix):
            return assign(slug, 'rule', f'sku_prefix:{prefix}', RULE_CONF['sku_prefix'], [slug], exempt=[slug])
    if trust and inp.nav_categories is not None:                             # 2a: the vendor's own navigable categories decide, when we have them (needs trust_vendor_path)
        if not inp.nav_categories:                                           # the vendor answered and gave none -> flag it, no slug, not a review
            return RouterOutput('uncategorized', None, 'rule', 'no_navigable_categories', RULE_CONF['navigable_categories'], ver, chash, None, None, slugs=[], uncategorized=True)
        slugs = nav_slugs(inp.nav_categories, res)
        if slugs: return assign_many(slugs, 'rule', 'navigable_categories', RULE_CONF['navigable_categories'], res.leaf)
        # codes present but none usable (excluded component leaf, not in our store, not a leaf): carry on with the rules below
    if inp.subject_type == 'product' and inp.item_code in (cfg.get('package_rules') or {}):   # 3
        slug = cfg['package_rules'][inp.item_code]
        return assign(slug, 'rule', f'package:{inp.item_code}', RULE_CONF['package'], [slug], exempt=[slug])
    if (inp.item_class or '').strip() in (cfg.get('review_classes') or []):                    # 4
        return review('review_class', stage='review', rule='review_class')
    for nr in (cfg.get('name_rules') or []):                                                 # 4a: product name states the answer, e.g. '<size> Mattress'
        m = re.search(nr['pattern'], inp.name or '', re.I)
        if m:
            slug = nr['template'].format(**{k: re.sub(r'\s+', '-', v.lower()) for k, v in m.groupdict().items() if v})
            if slug in res.leaf and slug in res.store and slug not in res.excluded and slug not in res.inactive:
                return assign(slug, 'rule', 'name_rule', RULE_CONF['name_rule'], res.leaf)
    cr = cfg.get('component_rule')                                                           # 4b: Component SKUs follow Ashley's own parts category
    comp_only = False                  # an Item (not a Component) whose Ashley path leads only to excluded leaves, e.g. component-skus-*
    if trust and cr and (inp.item_type or '') != cr['item_type'] and cr.get('items_with_only_component_path'):
        _lv = [x for x in dict.fromkeys(res.code_slug.get(c, c) for c in (inp.vendor_category_path or [])) if x in res.leaf]
        comp_only = bool(_lv) and all(x in res.excluded for x in _lv)
    if trust and cr and ((inp.item_type or '') == cr['item_type'] or comp_only):
        comp = [x for x in dict.fromkeys(res.code_slug.get(c, c) for c in (inp.vendor_category_path or []))
                if x.startswith(cr['slug_prefix']) and x in res.leaf and x in res.store and x not in res.inactive]
        if comp: return assign(comp[0], 'rule', 'component_sku', RULE_CONF['vendor_path'], [comp[0]], exempt=[comp[0]])
    if trust:
        for code in (inp.vendor_category_path or []):                                        # 5
            if code in res.vendor_map and res.vendor_map[code] not in res.excluded:    # excluded targets are skipped, not assigned
                return assign(res.vendor_map[code], 'rule', 'vendor_map', RULE_CONF['vendor_map'], res.leaf)
        leaves = [s for s in dict.fromkeys(res.code_slug.get(c, c) for c in (inp.vendor_category_path or []))
                  if s in res.leaf and s in res.store and s not in res.excluded]
        if len(leaves) == 1:                                                                 # 6
            slug = leaves[0]
            for c in cfg.get('contradictions') or []:
                if slug.startswith(c['slug_prefix']) and re.search(c['name_pattern'], inp.name or '', re.I):
                    return review('contradiction', [{'slug': slug}], stage='rule', rule='vendor_path_exact')
            return assign(slug, 'rule', 'vendor_path_exact', RULE_CONF['vendor_path'], res.leaf)
        if len(leaves) >= 2 and cfg['settings'].get('name_match_tiebreak'):                  # 6b (off unless enabled in the vendor config)
            slug = pick_by_name(inp.name, leaves)
            if slug: return assign(slug, 'rule', 'path_leaf_name_match', RULE_CONF['vendor_path'], res.leaf)
    icm = res.item_class_map.get((inp.item_class or '').strip())                            # 6c: itemClass that always lands in one category (works with the Ashley path off too)
    if icm and icm in res.leaf and icm in res.store and icm not in res.excluded and icm not in res.inactive:
        return assign(icm, 'rule', 'item_class_map', RULE_CONF['item_class'], res.leaf)
    options, why = options_for(inp, res, trust)                                              # 7
    if not options: return review('no_pool')
    if model is None:
        return review('no_rule_no_model', [{'slug': s} for s in options[:5]])
    if not ((inp.name or '').strip() or (inp.description or '').strip()):                    # nothing to read: don't pay for a guess
        return review('no_text', [{'slug': s} for s in options[:5]])
    ans = model.classify(inp, options)                                                       # 8
    probs = ans.get('probabilities') or {}
    top5 = [{'slug': s, 'p': round(p, 4)} for s, p in sorted(probs.items(), key=lambda kv: -kv[1]) if s != NONE_OF_THESE][:5]
    choice = ans.get('choice')
    if choice == NONE_OF_THESE: return review('none_of_these', top5, stage='model', rule='model_pool')
    if choice not in options: return review('not_offered', top5, stage='model', rule='model_pool')
    mm = cfg['settings'].get('min_margin')                                                   # Jev gives a probability for every option: refuse a near tie
    if mm:
        rivals = [p for s_, p in probs.items() if s_ != choice]
        if rivals and float(probs.get(choice, 0.0)) - max(rivals) < float(mm):
            return review('too_close', top5, stage='model', rule='model_pool')
    conf = min(float(probs.get(choice, 0.0)), MODEL_CAP)
    if not K.model_decision_ok(conf, threshold_for(cfg, len(options))):
        return review('below_threshold', top5, stage='model', rule='model_pool')
    return assign(choice, 'model', 'model_pool', conf, options, cands=top5)

# ---------------------------------------------------------------- resources and evaluation (dump based)
def _csv_any(path):
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, newline='', encoding=enc) as f: return list(csv.DictReader(f))
        except UnicodeDecodeError: continue

def resources_from_dump(cfg, dump, unreviewed_map=False):
    from dumpreader import rows
    pc = [c for c in rows(dump, 'pim_categories') if not c['deleted_at']]
    live = [c for c in pc if c['enabled'] == 1]
    parents = {str(c['parent_id']) for c in live}
    leaf = {c['slug'] for c in live if str(c['id']) not in parents}
    store_rows = [c for c in rows(dump, 'categories') if not c['deleted_at']]
    store = {c['slug'] for c in store_rows}
    inactive = {c['slug'] for c in store_rows if c['status'] != 1} | {c['slug'] for c in pc if c['enabled'] != 1}
    excluded = set(cfg.get('excluded_slugs') or [])
    for pre in (cfg.get('excluded_slug_prefixes') or []):          # e.g. component-skus-: children of an excluded parent
        excluded |= {sl for sl in (leaf | store) if sl.startswith(pre)}
    pools = {}
    pf = os.path.join(HERE, cfg['pools_file'])
    for cls, p in json.load(open(pf, encoding='utf-8'))['pools'].items():
        opts = [o['slug'] for o in sorted(p['options'], key=lambda o: -(o.get('support') or 0))
                if o['slug'] in leaf and o['slug'] in store and o['slug'] not in excluded]
        if opts: pools[cls.strip()] = opts
    vmap, cmap, labels = {}, {}, {}
    for r in _csv_any(os.path.join(HERE, cfg['vendor_map_file'])):
        rv = (r.get('REVIEW (Y/N/slug)') or '').strip(); slug = r.get('master_slug') or ''
        if r.get('status') == 'match' and r.get('leaf_or_parent') == 'LEAF' and slug: cmap[r['ashley_category']] = slug
        if slug and r.get('vendor_name'): labels[slug] = r['vendor_name']
        if rv.upper() == 'N': continue
        if rv.upper() == 'Y' or (not rv and unreviewed_map and r.get('status') == 'match' and r.get('leaf_or_parent') == 'LEAF'): vmap[r['ashley_category']] = slug
        elif rv and rv.upper() != 'Y': vmap[r['ashley_category']] = rv
    icm = {}
    if cfg.get('item_class_map_file') and os.path.exists(os.path.join(HERE, cfg['item_class_map_file'])):
        icm = {r['item_class'].strip(): r['slug'] for r in _csv_any(os.path.join(HERE, cfg['item_class_map_file'])) if r.get('slug')}
    return Resources(cfg, leaf, store, inactive, excluded, pools, vmap, MemoryStore(), cmap, icm, labels)

def inputs_from_dump(dump, skus, vendor_id, navcats=None):
    """RouterInputs for raw items by SKU. vendor_category_path = the real navigableCategories codes when navcats
    (from load_navcats) has the SKU; otherwise the item's existing category links.
    The Ashley API returns navigableCategories, but pim_raw_items in the dump does not store them (no column,
    nothing in rawitem_json), so for now the links the importer built from them stand in. Pass navcats
    (fetch_navcats.py output) to test the vendor-path rules on the real Ashley paths."""
    from dumpreader import rows
    raw = {r['sku']: r for r in rows(dump, 'pim_raw_items') if not r['is_deleted'] and r['sku'] in skus}
    uu = {r['uuid']: r['sku'] for r in raw.values()}
    slug = {c['uuid']: c['slug'] for c in rows(dump, 'pim_categories')}
    path = C.defaultdict(list)
    for r in rows(dump, 'pim_raw_item_categories'):
        if r['raw_item_id'] in uu and r['category_id'] in slug: path[uu[r['raw_item_id']]].append(slug[r['category_id']])
    code = {p['uuid']: p['item_code'] for p in rows(dump, 'pim_products')}
    icode = {}
    for r in rows(dump, 'pim_product_raw_items'):
        if r['raw_item_id'] in uu and code.get(r['product_id']): icode.setdefault(uu[r['raw_item_id']], code[r['product_id']])
    out = {}
    for sku, r in raw.items():
        out[sku] = RouterInput(vendor_id, 'raw_item', r['uuid'], sku, (r['itemName'] or r['itemFriendlyDesc'] or '').strip(),
                               r['itemDesc'], r['itemType'], (r['itemClass'] or '').strip(), icode.get(sku), (navcats[sku] if navcats and sku in navcats else path.get(sku, [])),
                               nav_categories=(navcats[sku] if navcats and sku in navcats else None))
    return out

def load_golden(path):
    """The other team's golden.jsonl -> rows shaped like gold.csv rows, plus 'accept' (every accepted slug)."""
    out = []
    with open(path, encoding='utf-8-sig') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r.get('sku') and r.get('accept'):
                    out.append({'row_id': r['sku'], 'sku': r['sku'], 'name': '', 'gold_slug': r['accept'][0], 'accept': list(r['accept']), 'status': 'golden'})
    return out

def golden_key(accept, picks, options):
    """Golden lists every accepted slug. Report one key per row so the existing comparisons (pick == key) keep working:
    the accepted slug the router picked, else the first accepted slug that was among its options, else the first accepted."""
    for a in accept:
        if a in picks: return a
    return next((a for a in accept if a in options), accept[0])

def evaluate(args):
    cfg = K.load_vendor_config(args.vendor)
    res = resources_from_dump(cfg, args.dump, args.unreviewed_map)
    if args.golden: gold = load_golden(args.golden)                           # answer key = golden.jsonl (a row is right if the pick is ANY accepted slug)
    else: gold = [r for r in _csv_any(os.path.join(HERE, 'gold', 'gold.csv'))
                  if r['status'] in ('gold', 'gold_flagged', 'gold_ruled', 'rule_handled')]
    navcats = load_navcats(args.navcats) if args.navcats else None
    inputs = inputs_from_dump(args.dump, {r['sku'] for r in gold}, cfg['vendor_id'], navcats)
    trust = args.trust_vendor_path; rowsout = []
    model = make_model(args, cfg)                                    # same builder as shadow: jev / openai-compat / anthropic
    if model is not None and hasattr(model, 'labels'): model.labels = res.labels
    for g in gold:
        inp = inputs.get(g['sku'])
        if not inp: continue
        out = route(inp, res, model, trust)
        opts, why = options_for(inp, res, trust)
        key = g['gold_slug']
        if g.get('accept'):
            picks = set(out.slugs or []) | {c['slug'] for c in (out.candidates or [])[:1]}
            key = golden_key(g['accept'], picks, opts)
        rowsout.append(dict(row_id=g['row_id'], name=(g['name'] or inp.name or '')[:40], gold=key, outcome=out.outcome, stage=out.stage, rule=out.rule,
                            slug=out.primary_slug or '', reason=out.review_reason or '', n_options=len(opts), options_from=why,
                            gold_in_options=(key in opts) if key != "__none__" else '',
                            correct=((key in (out.slugs or [])) or (out.outcome == 'uncategorized' and key == '__none__')),
                            slugs=' | '.join(out.slugs or []), n_slugs=len(out.slugs or []), uncategorized=out.uncategorized,
                            item_type=inp.item_type or '', item_class=inp.item_class or '',
                            undecided_why=undecided_why(inp, res) if out.outcome == 'review' else '',
                            model_pick=(out.candidates[0]['slug'] if out.stage == 'model' and out.candidates else (out.primary_slug if out.stage == 'model' else '')),
                            model_conf=(out.candidates[0].get('p', '') if out.stage == 'model' and out.candidates else ''),
                            vendor_path=' | '.join(inp.vendor_category_path or []),
                            path_leaves=' | '.join(usable_leaves(inp, res))))
    L = [f'# Cascade evaluation (trust_vendor_path={trust}, unreviewed_map={args.unreviewed_map}, model step off)', '',
         f'Rows scored: {len(rowsout)} of {len(gold)} answer-key rows ({len(gold) - len(rowsout)} had no raw item in the dump)', '']
    comp_rows = [r for r in rowsout if r['rule'] == 'component_sku' and r['outcome'] == 'assigned']
    asg = [r for r in rowsout if r['outcome'] == 'assigned' and r['rule'] != 'component_sku']
    L += ['## Decided by rules (assigned)', '', '| rule | decided | correct | precision |', '|---|---|---|---|']
    for rule in sorted({r['rule'] for r in asg}):
        g = [r for r in asg if r['rule'] == rule]; k = sum(r['correct'] for r in g)
        L.append(f'| {rule} | {len(g)} | {k} | {k / len(g):.1%} |')
    if asg: L.append(f'| **all rules** | {len(asg)} | {sum(r["correct"] for r in asg)} | {sum(r["correct"] for r in asg) / len(asg):.1%} |')
    gl = cfg['settings'].get('go_live') or {}
    target, min_rows = float(gl.get('precision_target', 0.99)), int(gl.get('min_rows', 30))
    def wilson_low(k, n, z=1.96):
        if not n: return 0.0
        p = k / n; d = 1 + z * z / n
        return (p + z * z / (2 * n) - z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5) / d
    if asg:
        L += ['', f'## Go-live check (target precision {target:.0%}, at least {min_rows} gold rows)', '',
              '| rule | rows | precision | 95% lower bound | verdict |', '|---|---|---|---|---|']
        for rule in sorted({r['rule'] for r in asg}):
            g = [r for r in asg if r['rule'] == rule]; k = sum(r['correct'] for r in g); n = len(g)
            v = 'shadow only: too few gold rows' if n < min_rows else ('ok to enable' if k / n >= target else 'below target')
            L.append(f'| {rule} | {n} | {k / n:.1%} | {wilson_low(k, n):.1%} | {v} |')
        L += ['', 'The lower bound is the plain-statistics floor on true precision given only these rows. A rule can pass the target here and still have a lower bound under it; the labeled rows are also the ones the rules were tuned on, so treat precision as optimistic.']
    if comp_rows:
        L += ['', '## Components (decision A: follow Ashley\'s component-skus-* category)', '',
              f'{len(comp_rows)} Component rows assigned by rule component_sku. Not scored against the key: the key labels them with real categories, by design.',
              f'The key says "no category" for {sum(r["gold"] == "__none__" for r in comp_rows)} of them (check those).']
        for slug, n in sorted(C.Counter(r['slug'] for r in comp_rows).items()): L.append(f'- {slug}: {n}')
    multi = [r for r in asg if r['n_slugs'] > 1]
    if multi: L += ['', f'## Several categories per product', '', f'{len(multi)} of {len(asg)} rule-assigned rows got more than one category (largest: {max(r["n_slugs"] for r in multi)}). A row counts as correct when the key slug is any of its categories.']
    unc = [r for r in rowsout if r['outcome'] == 'uncategorized']
    L += ['', f'## Uncategorized (vendor gave no navigable categories): {len(unc)}']
    if unc: L += ['', f'The key says "no category" for {sum(r["gold"] == "__none__" for r in unc)} of them; the other {sum(r["gold"] != "__none__" for r in unc)} have a real key answer (check those).']
    rev = [r for r in rowsout if r['outcome'] == 'review']
    L += ['', f'## Not decided: {len(rev)}', '', '| reason | rows | of which the key says "no category" |', '|---|---|---|']
    for reason in sorted({r['reason'] for r in rev}):
        g = [r for r in rev if r['reason'] == reason]; L.append(f'| {reason} | {len(g)} | {sum(r["gold"] == "__none__" for r in g)} |')
    if rev:
        L += ['', '## Why the rules left them undecided', '', '| why | itemType | rows | key says "no category" | key answer is among the options |', '|---|---|---|---|---|']
        for k, n in sorted(C.Counter((r['undecided_why'], r['item_type']) for r in rev).items(), key=lambda kv: -kv[1]):
            g = [r for r in rev if (r['undecided_why'], r['item_type']) == k]
            real = [r for r in g if r['gold'] != '__none__']
            L.append(f"| {k[0]} | {k[1]} | {n} | {len(g) - len(real)} | {sum(1 for r in real if r['gold_in_options'] is True)} of {len(real)} |")
    sl = [r for r in rev if r['undecided_why'] == 'several_leaves' and r['gold'] != '__none__']
    if sl:
        lv = [r['path_leaves'].split(' | ') for r in sl]
        inn = sum(r['gold'] in l for r, l in zip(sl, lv))
        L += ['', '## Could a tie-break rule pick among several path leaves?', '',
              f'{len(sl)} rows. Key is among the path leaves for {inn}. If the rule always took:',
              f'- the first leaf (deepest path first): {sum(r["gold"] == l[0] for r, l in zip(sl, lv))} correct',
              f'- the last leaf: {sum(r["gold"] == l[-1] for r, l in zip(sl, lv))} correct']
    mb = [r for r in rev if r['reason'] == 'no_rule_no_model' and r['gold'] != '__none__']
    if mb:
        rec = sum(1 for r in mb if r['gold_in_options'] is True)
        sizes = C.Counter('<=3' if r['n_options'] <= 3 else '4-8' if r['n_options'] <= 8 else '9+' for r in mb)
        L += ['', '## Would go to the model', '', f'{len(mb)} rows with a real answer. **The right category is among the options for {rec} of them ({rec / len(mb):.1%})** (best the model step can do).',
              f'Options offered: {dict(sizes)}']
        miss = [r for r in mb if r['gold_in_options'] is not True]
        for r in miss[:10]: L.append(f"- missing: {r['row_id']} {r['name']} | key={r['gold']} | {r['n_options']} options from {r['options_from']}")
    mp = [r for r in rowsout if r['stage'] == 'model' and r['model_pick'] and r['gold'] != '__none__']
    if args.use_model:
        L += ['', '## Model picks (step 8; thresholds are null, so every pick goes to review)', '',
              f'{len(mp)} rows with a model pick and a real key answer; {sum(r["model_pick"] == r["gold"] for r in mp)} match the key.']
        mpi = [r for r in mp if r['item_type'] != 'Component']
        L.append(f'Excluding Component rows (decision A routes those by rule when the vendor path is trusted): {sum(r["model_pick"] == r["gold"] for r in mpi)} of {len(mpi)} match the key.')
        if mp:
            L += ['', '| stated confidence | picks | match the key |', '|---|---|---|']
            for lo, hi in ((0, .7), (.7, .85), (.85, .95), (.95, 1.01)):
                g = [r for r in mp if r['model_conf'] != '' and lo <= float(r['model_conf']) < hi]
                if g: L.append(f"| {lo:.2f} to {min(hi, 1):.2f} | {len(g)} | {sum(r['model_pick'] == r['gold'] for r in g)} |")
        if len(mp) < 30: L += ['', f'Only {len(mp)} rows: too few to set a threshold (Phase 5 needs about 30 to 50).']
        L += [f'Model calls this run: {model.calls}']
        if model.errors: L += ['', f'**Model errors (rows sent to review): {model.errors}**', f'First error: {model.first_error}']
    os.makedirs(os.path.join(HERE, 'reports'), exist_ok=True)
    tag = ('trust' if trust else 'independent') + ('_unreviewed_map' if args.unreviewed_map else '') + ('_navcats' if args.navcats else '') + ('_golden' if args.golden else '') + ('_model' if args.use_model else '')
    with open(os.path.join(HERE, 'reports', f'cascade_eval_{tag}.md'), 'w', encoding='utf-8') as f: f.write('\n'.join(L) + '\n')
    with open(os.path.join(HERE, 'reports', f'cascade_eval_{tag}_rows.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rowsout[0])); w.writeheader(); w.writerows(rowsout)
    print('\n'.join(L))

SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS router_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, vendor_id TEXT, subject_type TEXT, subject_uuid TEXT, sku TEXT,
  content_hash TEXT, primary_slug TEXT, outcome TEXT, stage TEXT, rule TEXT, confidence REAL, version TEXT, decided_by TEXT DEFAULT 'system',
  status TEXT DEFAULT 'shadow', candidates TEXT, invalidated_reason TEXT, slugs TEXT, uncategorized INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS router_review_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, vendor_id TEXT, subject_type TEXT, subject_uuid TEXT, sku TEXT,
  content_hash TEXT, reason TEXT, candidates TEXT, decision_id INTEGER, status TEXT DEFAULT 'open');
"""

def make_model(args, cfg):
    """Build the step-8 model from the command-line options, or None when --use-model is not given."""
    if not getattr(args, 'use_model', False): return None
    import model_step as MS
    cap = args.max_model_calls or cfg['settings'].get('model_spend_cap_per_batch')
    os.makedirs(os.path.join(HERE, 'reports'), exist_ok=True)
    cache = os.path.join(HERE, 'reports', 'model_cache.json')          # answers are cached by prompt, so a rerun costs nothing
    if args.provider == 'jev':
        key = os.environ.get('OPENROUTER_API_KEY') or os.environ.get('TYPESAFE_API_KEY')
        if not key: raise SystemExit('Set OPENROUTER_API_KEY (or TYPESAFE_API_KEY with --base-url) before using --use-model with Jev.')
        return MS.JevModel(model=args.model_name, endpoint=args.base_url, api_key=key, max_calls=cap, cache_path=cache,
                           min_interval=args.pause_seconds, tie_prefer=cfg.get('tie_prefer'))
    if args.provider == 'openai-compat':
        if not (args.base_url and args.model_name): raise SystemExit('--provider openai-compat needs --base-url and --model-name')
        return MS.OpenAICompatModel(args.model_name, args.base_url, max_calls=cap, cache_path=cache, min_interval=args.pause_seconds, tie_prefer=cfg.get('tie_prefer'))
    return MS.LLMModel(model=args.model_name or MS.DEFAULT_MODEL, max_calls=cap, cache_path=cache, tie_prefer=cfg.get('tie_prefer'))

def shadow(args):
    """Record what the router WOULD do, into router_decisions (status 'shadow'). Applies nothing.
    --db sqlite:reports/shadow.db  : local trial file, no MySQL needed.
    --db mysql://user:pass@host/dbname : the real tables from contract/schema.sql (needs: pip install pymysql)."""
    from decision_store import SqlDecisionStore, run_shadow
    cfg = K.load_vendor_config(args.vendor)
    res = resources_from_dump(cfg, args.dump, False)
    gold = [r for r in _csv_any(os.path.join(HERE, 'gold', 'gold.csv'))
            if r['status'] in ('gold', 'gold_flagged', 'gold_ruled', 'rule_handled')]
    navcats = load_navcats(args.navcats) if args.navcats else None
    if args.skus:                                   # a text file, one SKU per line
        wanted = {l.strip() for l in open(args.skus, encoding='utf-8') if l.strip()}
    elif args.all:                                  # every non-deleted raw item in the dump
        from dumpreader import rows
        wanted = {r['sku'] for r in rows(args.dump, 'pim_raw_items') if not r['is_deleted'] and r['sku']}
    else:
        wanted = {r['sku'] for r in gold}           # default: the answer-key SKUs only
    inputs = list(inputs_from_dump(args.dump, wanted, cfg['vendor_id'], navcats).values())
    print(f'shadow: routing {len(inputs)} of {len(wanted)} requested SKUs')
    if args.db.startswith('sqlite:'):
        import sqlite3
        conn = sqlite3.connect(args.db[7:]); conn.executescript(SQLITE_DDL)
        for col in ('slugs TEXT', 'uncategorized INTEGER DEFAULT 0'):          # shadow.db made before multi-category support
            try: conn.execute(f'ALTER TABLE router_decisions ADD COLUMN {col}')
            except sqlite3.OperationalError: pass
        st = SqlDecisionStore(conn, '?')
    elif args.db.startswith('mysql://'):
        import pymysql, urllib.parse as U
        u = U.urlparse(args.db)
        conn = pymysql.connect(host=u.hostname, port=u.port or 3306, user=U.unquote(u.username or ''), password=U.unquote(u.password or ''), database=u.path.lstrip('/'))
        st = SqlDecisionStore(conn, '%s')
    else: raise SystemExit('--db must start with sqlite: or mysql://')
    if args.golden_map:
        res.golden = {r['sku']: r['accept'] for r in load_golden(args.golden_map)}
        print(f'golden map: {len(res.golden)} SKUs, {sum(1 for i in inputs if i.sku in res.golden)} of the routed products are in it')
    model = make_model(args, cfg)
    if model is not None and hasattr(model, 'labels'): model.labels = res.labels
    n = run_shadow(inputs, lambda i: route(i, res, model, args.trust_vendor_path), st)
    print(f'shadow run: {len(inputs)} items, {n["assigned"]} assigned, {n.get("uncategorized", 0)} uncategorized, {n["review"]} to review. Nothing was applied.')
    for rule, outcome, k in st.counts_by_rule(cfg['vendor_id'], str(cfg['version'])): print(f'  {rule:28s} {outcome:9s} {k}')
    if model:
        print(f'model calls this run: {model.calls}' + (f' | errors: {model.errors} | first error: {model.first_error}' if model.errors else ''))
        print('thresholds are ' + ('not set, so every model pick is recorded as review with its stated confidence' if not cfg['settings'].get('thresholds') else 'set'))

def compare(args):
    """Shadow decisions vs the product's current category links in the dump. Read-only. Says where the router's pick
    is already one of the product's categories and where applying it would add something new."""
    import sqlite3
    from dumpreader import rows
    cfg = K.load_vendor_config(args.vendor)
    conn = sqlite3.connect(args.db[7:])
    dec = [(s, u, json.loads(sl) if sl else [p], r) for s, u, p, r, sl in conn.execute(
        "SELECT sku, subject_uuid, primary_slug, rule, slugs FROM router_decisions WHERE status='shadow' AND outcome='assigned' AND vendor_id=?", (cfg['vendor_id'],)).fetchall()]
    slug = {r['uuid']: r['slug'] for r in rows(args.dump, 'pim_categories')}
    prod_of = {}
    for r in rows(args.dump, 'pim_product_raw_items'): prod_of.setdefault(r['raw_item_id'], r['product_id'])
    links = C.defaultdict(set)
    for r in rows(args.dump, 'pim_product_categories'):
        if r['category_id'] in slug: links[r['product_id']].add(slug[r['category_id']])
    out, by = [], C.defaultdict(C.Counter)
    for sku, uuid, pick, rule in dec:
        p = prod_of.get(uuid); cur = links.get(p, set()) if p else set()
        state = 'no_product' if not p else ('already_linked' if set(pick) <= cur else ('product_has_no_links' if not cur else 'would_add'))
        by[rule][state] += 1; out.append(dict(sku=sku, rule=rule, pick=' | '.join(pick), state=state, current=' | '.join(sorted(cur))))
    L = ['# Shadow decisions vs current category links (read-only)', '',
         '| rule | already linked | would add a category | product has no links | no product |', '|---|---|---|---|---|']
    for rule, cn in sorted(by.items()):
        L.append(f"| {rule} | {cn['already_linked']} | {cn['would_add']} | {cn['product_has_no_links']} | {cn['no_product']} |")
    os.makedirs(os.path.join(HERE, 'reports'), exist_ok=True)
    with open(os.path.join(HERE, 'reports', 'shadow_compare.md'), 'w', encoding='utf-8') as f: f.write('\n'.join(L) + '\n')
    with open(os.path.join(HERE, 'reports', 'shadow_compare_rows.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['sku', 'rule', 'pick', 'state', 'current']); w.writeheader(); w.writerows(out)
    print('\n'.join(L))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('eval')
    e.add_argument('--dump', default=os.path.join(HERE, 'dump_for_evidence.sql'))
    e.add_argument('--vendor', default=os.path.join(HERE, 'vendors', 'ashley.yaml'))
    e.add_argument('--navcats', help='CSV from fetch_navcats.py (sku, navigableCategories); uses real Ashley paths')
    e.add_argument('--golden', help='score against golden.jsonl (the other team\'s key) instead of gold/gold.csv')
    e.add_argument('--trust-vendor-path', action='store_true'); e.add_argument('--unreviewed-map', action='store_true')
    e.add_argument('--use-model', action='store_true', help='run step 8 (Jev: needs OPENROUTER_API_KEY); picks go to review while thresholds are null')
    e.add_argument('--max-model-calls', type=int, default=None)
    e.add_argument('--provider', choices=['jev', 'anthropic', 'openai-compat'], default='jev')
    e.add_argument('--model-name', default=None, help='jev: default typesafe/jev-1.14; openai-compat: e.g. ministral-3:14b on Ollama, mistralai/ministral-14b-2512 on OpenRouter')
    e.add_argument('--pause-seconds', type=float, default=0.2, help='minimum gap between calls (raise it if you see HTTP 429 rate limits)')
    e.add_argument('--base-url', default=None, help='jev: full endpoint, default OpenRouter Decisions API; openai-compat: e.g. http://localhost:11434/v1')
    s = sub.add_parser('shadow')
    s.add_argument('--dump', default=os.path.join(HERE, 'dump_for_evidence.sql'))
    s.add_argument('--vendor', default=os.path.join(HERE, 'vendors', 'ashley.yaml'))
    s.add_argument('--navcats'); s.add_argument('--trust-vendor-path', action='store_true')
    s.add_argument('--golden-map', help='golden.jsonl: map every SKU it lists to its first valid accepted category (step 1a); the rest go through the normal cascade')
    s.add_argument('--all', action='store_true', help='route every product in the dump, not just the answer-key SKUs')
    s.add_argument('--skus', help='text file with one SKU per line (e.g. test_sku.txt)')
    s.add_argument('--use-model', action='store_true', help='also run step 8 on what the rules leave (needs ANTHROPIC_API_KEY, or --provider openai-compat)')
    s.add_argument('--max-model-calls', type=int, default=None, help='stop calling the model after this many calls; the rest go to review')
    s.add_argument('--provider', choices=['jev', 'anthropic', 'openai-compat'], default='jev')
    s.add_argument('--model-name', default=None, help='jev: default typesafe/jev-1.14')
    s.add_argument('--base-url', default=None, help='jev: full endpoint, default OpenRouter Decisions API; openai-compat: e.g. http://localhost:11434/v1')
    s.add_argument('--pause-seconds', type=float, default=0.2, help='minimum gap between calls (raise it on HTTP 429)')
    s.add_argument('--db', required=True, help='sqlite:reports/shadow.db  or  mysql://user:pass@host/dbname')
    k = sub.add_parser('compare')
    k.add_argument('--dump', default=os.path.join(HERE, 'dump_for_evidence.sql'))
    k.add_argument('--vendor', default=os.path.join(HERE, 'vendors', 'ashley.yaml'))
    k.add_argument('--db', required=True, help='sqlite:reports/shadow.db (the file shadow wrote)')
    a = ap.parse_args(); {'eval': evaluate, 'shadow': shadow, 'compare': compare}[a.cmd](a)

if __name__ == '__main__': main()