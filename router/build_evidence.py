#!/usr/bin/env python3
"""Evidence builder (pools, vendor map, packages, uncategorized breakdown). Re-runnable for any store dump.
Usage: python build_evidence.py DUMP.sql [OUT_DIR] [--min-support N] [--config vendors/ashley.yaml]
Writes (OUT_DIR, default evidence_out):
  pools.json / pool_summary.csv / pool_dropped_pairs.csv  leaf-only item-class pools
  vendor_map_reviewed.csv                                  vendor category -> master slug (review column)
  packages.csv                                             package products + current set link
  store_uncategorized_breakdown.csv / .md                  why 2,744-style products have no category
"""
import sys, os, re, csv, json, collections as C
from dumpreader import rows

import argparse, yaml
_p = argparse.ArgumentParser(); _p.add_argument('dump'); _p.add_argument('out', nargs='?', default='evidence_out')
_p.add_argument('--min-support', type=int, default=2)
_p.add_argument('--config', default=None, help='vendor yaml: review_classes, parent_fallback')
_a = _p.parse_args(); DUMP, OUT, MIN_SUP = _a.dump, _a.out, _a.min_support
CFG = yaml.safe_load(open(_a.config, encoding='utf-8')) if _a.config else {}
REVIEW_CLASSES = {c.strip() for c in (CFG.get('review_classes') or [])}
PARENT_FALLBACK = CFG.get('parent_fallback', True)
os.makedirs(OUT, exist_ok=True)
EXCLUDED = {'component-skus', 'uncategorized', 'store-displays'}
def w(name, hdr, data):
    with open(os.path.join(OUT, name), 'w', newline='') as f:
        c = csv.writer(f); c.writerow(hdr); c.writerows(data)

pim_cat = list(rows(DUMP, 'pim_categories')); st_cat = list(rows(DUMP, 'categories'))
live = [c for c in pim_cat if c['enabled'] == 1 and not c['deleted_at']]
by_id = {str(c['id']): c for c in pim_cat}; by_uuid = {c['uuid']: c for c in pim_cat}
parents = {str(c['parent_id']) for c in live}
is_leaf = lambda c: str(c['id']) not in parents
store_uuid = {c['uuid'] for c in st_cat if not c['deleted_at'] and c['status'] == 1}
leaf = {c['uuid']: c for c in live if is_leaf(c) and c['slug'] not in EXCLUDED}

# ---------- 1. pools (leaf-only, min support) ----------
raw = [r for r in rows(DUMP, 'pim_raw_items') if not r['is_deleted']]
cls_of = {r['uuid']: (r['itemClass'] or '').strip() for r in raw}
sup = C.defaultdict(C.Counter); sup_par = C.defaultdict(C.Counter); n_items = C.Counter(cls_of.values())
children = C.defaultdict(list)
for c in live: children[str(c['parent_id'])].append(c)
def leaves_under(c):
    out, stack = [], [c]
    while stack:
        x = stack.pop(); kids = children.get(str(x['id']), [])
        if kids: stack.extend(kids)
        elif x['slug'] not in EXCLUDED: out.append(x)
    return out
live_by_uuid = {c['uuid']: c for c in live}
seen = set()
for l in rows(DUMP, 'pim_raw_item_categories'):
    k = (l['raw_item_id'], l['category_id'])
    if k in seen or l['raw_item_id'] not in cls_of: continue
    seen.add(k)
    if l['category_id'] in leaf: sup[cls_of[l['raw_item_id']]][l['category_id']] += 1
    else:
        c = live_by_uuid.get(l['category_id'])          # parent-level link (not leaf, not excluded)
        if c and c['slug'] not in EXCLUDED and not is_leaf(c): sup_par[cls_of[l['raw_item_id']]][l['category_id']] += 1
pools, dropped, summ = {}, [], []
for cl in sorted(n_items):
    pairs = sup.get(cl, C.Counter())
    keep = {u: n for u, n in pairs.items() if n >= MIN_SUP}
    if pairs and not keep:                       # never leave a class empty: keep its best option
        u, n = pairs.most_common(1)[0]; keep = {u: n}
    for u, n in pairs.items():
        if u not in keep: dropped.append([cl, leaf[u]['slug'], n, n_items[cl]])
    opts = [{'slug': leaf[u]['slug'], 'support': n, 'in_store': u in store_uuid} for u, n in sorted(keep.items(), key=lambda x: -x[1])]
    source, parents_used = 'links', []
    if cl in REVIEW_CLASSES:
        opts, source = [], 'review_class'        # config says: never offer options, send to review
    elif not opts and PARENT_FALLBACK:
        pp = [u for u, n in sup_par.get(cl, C.Counter()).items() if n >= MIN_SUP]
        if pp:
            seen_s = {}
            for u in pp:
                parents_used.append(live_by_uuid[u]['slug'])
                for lf in leaves_under(live_by_uuid[u]): seen_s[lf['slug']] = lf
            opts = [{'slug': sl, 'support': None, 'in_store': x['uuid'] in store_uuid} for sl, x in sorted(seen_s.items())]
            source = 'parent_fallback'
    if not opts and source == 'links': source = 'none'
    pools[cl] = {'items': n_items[cl], 'source': source, 'parents': parents_used, 'options': opts}
    summ.append([cl, n_items[cl], len(pairs), len(opts), len(pairs) - len(opts) if source == 'links' else 0, sum(1 for o in opts if not o['in_store']), source])
json.dump({'min_support': MIN_SUP, 'pools': pools}, open(os.path.join(OUT, 'pools.json'), 'w'), indent=1)
w('pool_summary.csv', ['item_class', 'items', 'leaf_options_raw', 'options_kept', 'dropped_low_support', 'options_not_in_store', 'pool_source'], summ)
w('pool_dropped_pairs.csv', ['item_class', 'dropped_slug', 'support', 'class_items'], dropped)
bk = C.Counter()
for s in summ:
    k = s[3]; bk['0 (no pool)' if k == 0 else '1' if k == 1 else '2-5' if k <= 5 else '6-10' if k <= 10 else '11-15' if k <= 15 else '16+'] += s[1]
print('Items by pool size:', dict(bk)); print('Dropped pairs:', len(dropped))
print('Pool source (items):', dict(C.Counter({k: sum(x[1] for x in summ if x[6] == k) for k in {x[6] for x in summ}})))

# ---------- 2. vendor map ----------
def path_key(c):
    names = []; x = c
    while x:
        names.append(x['name']); x = by_id.get(str(x['parent_id']))
    return re.sub(r'[^A-Za-z0-9]', '', ''.join(reversed(names))).upper()
exact = C.defaultdict(list); derived = C.defaultdict(list)
for c in live:
    if c['ashley_category']: exact[c['ashley_category']].append(c)
    derived[path_key(c)].append(c)
vmap = []
for v in rows(DUMP, 'pim_vendor_categories'):
    k = v['ashley_category']; m, how = exact.get(k, []), 'exact_field'
    if not m: m, how = derived.get(k, []), 'derived_from_name_path'
    st = 'match' if len(m) == 1 else 'ambiguous' if m else 'none'
    c = m[0] if len(m) == 1 else None
    vmap.append([v['uuid'], v['vendor_id'], v['name'], k, st, how if m else '', c['slug'] if c else ';'.join(x['slug'] for x in m),
                 'LEAF' if c and is_leaf(c) else 'PARENT' if c else '', 'in_store' if c and c['uuid'] in store_uuid else ('NOT_IN_STORE' if c else ''), ''])
w('vendor_map_reviewed.csv', ['vendor_cat_uuid', 'vendor_id', 'vendor_name', 'ashley_category', 'status', 'matched_by', 'master_slug', 'leaf_or_parent', 'store_sync', 'REVIEW (Y/N/slug)'], vmap)
print('Vendor map:', dict(C.Counter(r[4] for r in vmap)), '| by method:', dict(C.Counter(r[5] for r in vmap if r[5])))

# ---------- 3. packages ----------
links = C.defaultdict(set)
for l in rows(DUMP, 'pim_product_categories'): links[l['product_id']].add(l['category_id'])
pk = []
for p in rows(DUMP, 'pim_products'):
    if 'package' in (p['item_code'] or '').lower():
        slugs = sorted(by_uuid[u]['slug'] for u in links.get(p['uuid'], ()) if u in by_uuid)
        sets = [s for s in slugs if s.endswith('sets') or s.endswith('-package')]
        pk.append([p['uuid'], p['item_code'], ';'.join(slugs), ';'.join(sets), 'ok' if len(sets) == 1 else 'NO_SET_LINK' if not sets else 'MULTI_SET'])
w('packages.csv', ['product_uuid', 'item_code', 'current_slugs', 'set_slugs', 'check'], pk)
print('Packages:', len(pk), dict(C.Counter(r[4] for r in pk)), '| item_codes:', dict(C.Counter(r[1] for r in pk)))

# ---------- 4. uncategorized store products ----------
sp = [p for p in rows(DUMP, 'products') if not p['deleted_at']]
sl = C.defaultdict(set)
for l in rows(DUMP, 'product_categories'): sl[l['product_id']].add(l['category_id'])
pim_u = {p['uuid'] for p in rows(DUMP, 'pim_products')}
by_p = {p['uuid']: p for p in sp}
bd = C.Counter(); ex = {}
for p in sp:
    if sl.get(p['uuid']): continue
    par = by_p.get(p['parent_id']) if p['parent_id'] not in (None, '', '0', 0) else None
    if par is not None: g = 'variation, parent HAS category (inherit)' if sl.get(par['uuid']) else 'variation, parent ALSO uncategorized'
    elif p['parent_id'] not in (None, '', '0', 0): g = 'variation, parent missing/deleted'
    else: g = 'parent/simple product, no category (router target)'
    key = (g, 'product_type=%s' % p['product_type'], 'status=%s' % p['status'], 'in_pim' if p['uuid'] in pim_u else 'not_in_pim')
    bd[key] += 1; ex.setdefault(key, p['sku'])
rowsb = [list(k) + [n, ex[k]] for k, n in bd.most_common()]
w('store_uncategorized_breakdown.csv', ['group', 'product_type', 'status', 'in_pim', 'products', 'example_sku'], rowsb)
print('Uncategorized store products:', sum(bd.values()))
for g, n in C.Counter({g: sum(n for k, n in bd.items() if k[0] == g) for g in {k[0] for k in bd}}).most_common(): print('  ', n, g)