#!/usr/bin/env python3
"""Data profile for the product->category router. Re-runnable for any store dump.
Usage: python data_profile.py DUMP.sql [OUT_DIR]
Writes OUT_DIR/data_profile.md plus CSVs. Reads rows directly from a mysqldump file."""
import sys, os, csv, collections as C
from dumpreader import rows

DUMP = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else 'phase0_out'
os.makedirs(OUT, exist_ok=True)
EXCLUDED_SLUGS = {'component-skus', 'uncategorized', 'store-displays'}
L = []
def say(s=''): L.append(s); print(s)
def table(hdr, data):
    say('| ' + ' | '.join(hdr) + ' |'); say('|' + '---|' * len(hdr))
    for r in data: say('| ' + ' | '.join(str(x) for x in r) + ' |')
def csvw(name, hdr, data):
    with open(os.path.join(OUT, name), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(data)

# ---------- load ----------
pim_cat = list(rows(DUMP, 'pim_categories'))
st_cat = list(rows(DUMP, 'categories'))
pim_prod = list(rows(DUMP, 'pim_products'))
st_prod = list(rows(DUMP, 'products'))
pim_pc = list(rows(DUMP, 'pim_product_categories'))
st_pc = list(rows(DUMP, 'product_categories'))
raw = list(rows(DUMP, 'pim_raw_items'))
vcat = list(rows(DUMP, 'pim_vendor_categories'))

say('# Data profile'); say()

# ---------- 1. categories ----------
say('## 1. Categories')
mcat = [c for c in pim_cat if c['enabled'] == 1 and not c['deleted_at']]
scat = [c for c in st_cat if not c['deleted_at']]
s_active = [c for c in scat if c['status'] == 1]
m_by_id = {str(c['id']): c for c in pim_cat}
m_by_uuid = {c['uuid']: c for c in pim_cat}
parents_m = {str(c['parent_id']) for c in mcat if str(c['parent_id']) not in ('0', '', 'None')}
top_m = [c for c in mcat if str(c['parent_id']) in ('0', '', 'None')]
is_parent = lambda c: str(c['id']) in parents_m
leaf_m = [c for c in mcat if not is_parent(c)]
table(['measure', 'pim_categories (master)', 'categories (store)'], [
    ['rows', len(pim_cat), len(st_cat)],
    ['active/enabled', len(mcat), len(s_active)],
    ['top-level (parent_id 0)', len(top_m), sum(1 for c in s_active if str(c['parent_id']) == '0')],
    ['has children (parents)', len({str(c['id']) for c in mcat if is_parent(c)}), '-'],
    ['leaf (no children)', len(leaf_m), '-'],
    ['slug unique', len({c['slug'] for c in mcat}) == len(mcat), len({c['slug'] for c in s_active}) == len(s_active)],
])
say()
m_uuid = {c['uuid'] for c in mcat}; s_uuid = {c['uuid'] for c in s_active}
only_m = [c for c in mcat if c['uuid'] not in s_uuid]
only_s = [c for c in s_active if c['uuid'] not in m_uuid]
say(f'Master-only (not synced to store): **{len(only_m)}** -> ' + ', '.join(c['slug'] for c in only_m))
say(f'Store-only: **{len(only_s)}** -> ' + ', '.join(c['slug'] for c in only_s)); say()
excl = [c for c in mcat if c['slug'] in EXCLUDED_SLUGS]
say('Excluded slugs present in master: ' + ', '.join(f"{c['slug']} (id {c['id']}, parent {c['parent_id']})" for c in excl)); say()
names = C.Counter(c['name'].strip().lower() for c in mcat)
dups = {n: k for n, k in names.items() if k > 1}
say(f'Duplicate category names among enabled master categories: **{len(dups)}**')
for n in sorted(dups):
    say(f'- "{n}": ' + ', '.join(f"{c['slug']} (parent {m_by_id.get(str(c['parent_id']),{}).get('name','-')})" for c in mcat if c['name'].strip().lower() == n))
say()
# a "leaf option" list = enabled leaf, not excluded
leaf_opts = [c for c in leaf_m if c['slug'] not in EXCLUDED_SLUGS]
say(f'Candidate leaf options for the router (enabled, leaf, not excluded): **{len(leaf_opts)}**'); say()
csvw('leaf_options.csv', ['id', 'uuid', 'slug', 'name', 'parent_slug', 'in_store'],
     [[c['id'], c['uuid'], c['slug'], c['name'], m_by_id.get(str(c['parent_id']), {}).get('slug', ''), c['uuid'] in s_uuid] for c in leaf_opts])

# ---------- 2. products and links ----------
say('## 2. Products and category links')
pp_by_uuid = {p['uuid']: p for p in pim_prod}
links = C.defaultdict(list)
for r in pim_pc: links[r['product_id']].append(r['category_id'])
say(f'pim_products: **{len(pim_prod)}**; with >=1 link in pim_product_categories: **{sum(1 for p in pim_prod if p["uuid"] in links)}**')
orphan = [u for u in links if u not in pp_by_uuid]
say(f'Link rows whose product is not in pim_products: **{len(orphan)}** products'); 
dist = C.Counter(len(set(links.get(p['uuid'], []))) for p in pim_prod)
table(['categories per pim_product', 'products'], sorted(dist.items()))
say()
cat_kind = C.Counter()
for p in pim_prod:
    for cu in set(links.get(p['uuid'], [])):
        c = m_by_uuid.get(cu)
        cat_kind['missing in master' if not c else ('parent' if is_parent(c) else ('excluded' if c['slug'] in EXCLUDED_SLUGS else 'leaf'))] += 1
say('Kind of category each existing pim link points to: ' + ', '.join(f'{k}={v}' for k, v in cat_kind.items())); say()
# products with a leaf link
no_leaf = [p for p in pim_prod if not any((m_by_uuid.get(cu) and not is_parent(m_by_uuid[cu]) and m_by_uuid[cu]['slug'] not in EXCLUDED_SLUGS) for cu in links.get(p['uuid'], []))]
say(f'pim_products with no usable leaf link: **{len(no_leaf)}**'); say()

s_links = C.defaultdict(set)
for r in st_pc: s_links[r['product_id']].add(r['category_id'])
s_live = [p for p in st_prod if not p['deleted_at']]
sd = C.Counter(len(s_links.get(p['uuid'], ())) for p in s_live)
say(f'Store products (not deleted): **{len(s_live)}** (parents/variations: product_type 1 = {sum(1 for p in s_live if p["product_type"]==1)}, simple = {sum(1 for p in s_live if p["product_type"]==0)})')
table(['categories per store product', 'products'], sorted(sd.items()))
say()
nocat_s = [p for p in s_live if not s_links.get(p['uuid'])]
say(f'Store products with no category: **{len(nocat_s)}**; of those, in pim_products: {sum(1 for p in nocat_s if p["uuid"] in pp_by_uuid)}, with pim link: {sum(1 for p in nocat_s if p["uuid"] in links)}'); say()
csvw('store_products_no_category.csv', ['uuid', 'sku', 'slug', 'product_type', 'status', 'parent_id', 'in_pim'],
     [[p['uuid'], p['sku'], p['slug'], p['product_type'], p['status'], p['parent_id'], p['uuid'] in pp_by_uuid] for p in nocat_s])

# ---------- 3. item_code / packages ----------
say('## 3. item_code (package signal) in pim_products')
ic = C.Counter((p['item_code'] or '').strip() for p in pim_prod)
table(['item_code', 'products'], ic.most_common(25)); say()
pkg = [p for p in pim_prod if 'package' in (p['item_code'] or '').lower()]
say(f'item_code containing "Package": **{len(pkg)}** products'); say()
# what do packages currently link to?
pk_cat = C.Counter()
for p in pkg:
    for cu in set(links.get(p['uuid'], [])):
        c = m_by_uuid.get(cu); pk_cat[c['slug'] if c else 'MISSING'] += 1
table(['category slug linked to packages', 'links'], pk_cat.most_common(20)); say()

# ---------- 4. raw items ----------
say('## 4. pim_raw_items signals')
live_raw = [r for r in raw if not r['is_deleted']]
say(f'Raw items: {len(raw)} (not deleted: {len(live_raw)})'); say()
table(['itemType', 'rows'], C.Counter((r['itemType'] or '').strip() for r in live_raw).most_common(15)); say()
cls = C.Counter((r['itemClass'] or '').strip() for r in live_raw)
say(f'Distinct itemClass values: **{len(cls)}**'); table(['itemClass', 'rows'], cls.most_common(15)); say()
say(f'itemisPackage values: {dict(C.Counter(r["itemisPackage"] for r in live_raw))}')
say(f'rows with non-empty `categories` text: {sum(1 for r in live_raw if (r["categories"] or "").strip())}'); say()
csvw('item_class_counts.csv', ['itemClass', 'rows'], cls.most_common())

# ---------- 5. vendor categories -> master by path ----------
say('## 5. pim_vendor_categories -> pim_categories (match by Ashley path)')
say(f'Rows: {len(vcat)}; vendors: {len({v["vendor_id"] for v in vcat})}; already mapped (pim_category_id set): {sum(1 for v in vcat if v["pim_category_id"] not in (None, "", "0"))}')
m_by_ash = C.defaultdict(list)
for c in mcat:
    if c['ashley_category']: m_by_ash[c['ashley_category']].append(c)
hit, miss, amb = [], [], []
for v in vcat:
    cands = m_by_ash.get(v['ashley_category'], [])
    (hit if len(cands) == 1 else amb if len(cands) > 1 else miss).append((v, cands))
say(f'Exact match on ashley_category: **{len(hit)}**; ambiguous: {len(amb)}; no match: **{len(miss)}**')
say('Unmatched: ' + '; '.join(f"{v['name']} [{v['ashley_category']}]" for v, _ in miss)); say()
csvw('vendor_map_proposed.csv', ['vendor_cat_uuid', 'vendor_name', 'ashley_parent', 'ashley_category', 'status', 'master_slug', 'master_uuid'],
     [[v['uuid'], v['name'], v['ashley_parent_category'], v['ashley_category'], 'match' if len(c) == 1 else ('ambiguous' if c else 'none'),
       ';'.join(x['slug'] for x in c), ';'.join(x['uuid'] for x in c)] for v, c in hit + amb + miss])

with open(os.path.join(OUT, 'data_profile.md'), 'w') as f: f.write('\n'.join(L))