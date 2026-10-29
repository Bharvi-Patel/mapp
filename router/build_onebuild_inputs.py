#!/usr/bin/env python3
"""Build the single-file inputs for the onebuild catalog from the loose files in router/. Run once, from the router folder:
    python build_onebuild_inputs.py
Writes onebuild/navcats.csv (THE one navcats file for this db: sku, navigableCategories, status), onebuild/amp_map.csv,
onebuild/approved_links.csv and onebuild/conflicts.csv (SKUs whose records disagree between files; read it).
Per SKU the first file that has it supplies the record, except that a failed fetch never beats an ok record. Nothing is deleted or changed."""
import csv, os, sys, collections as C
csv.field_size_limit(2**30 if os.name == 'nt' else sys.maxsize)
OUT = 'onebuild'
SOURCES = [                       # (role, file); the FIRST file that has a SKU supplies its record (an ok record beats a failed fetch)
    ('kit', 'navcats_kits.csv'),
    ('own', 'pim_vendor_api_ingestion_202610290943.csv'),
    ('variant', 'navcats_amp_default.csv'), ('variant', 'navcats_beds.csv'),
    ('variant', 'navcats_sectionals.csv'), ('variant', 'navcats_amp_rest.csv'),
    ('piece', 'navcats_demo.csv'),
]
MAPS = ['amp_master_map.csv', 'bed_amp_master_map.csv', 'amp_default_variant_map.csv']

def read(f):
    with open(f, encoding='utf-8-sig', newline='') as fh: return list(csv.DictReader(fh))

def main():
    rec, roles, seen = {}, C.defaultdict(set), C.defaultdict(list)
    for role, f in SOURCES:
        for r in read(f):
            sku = (r.get('sku') or '').strip()
            if not sku: continue
            row = (r.get('navigableCategories') or '', (r.get('status') or 'ok').strip())
            roles[sku].add(role); seen[sku].append((f, row))
            if sku not in rec or (rec[sku][1] != 'ok' and row[1] == 'ok'): rec[sku] = row     # first file wins, except that a failed fetch (bad_body, no_field...) never beats an ok record
    os.makedirs(OUT, exist_ok=True)
    order = ['kit', 'own', 'variant', 'piece']
    with open(f'{OUT}/navcats.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(['sku', 'navigableCategories', 'status'])
        for sku in sorted(rec): w.writerow([sku, rec[sku][0], rec[sku][1]])
    conf = [(sku, f, v[0], v[1]) for sku, lst in seen.items() if len({v for _, v in lst}) > 1 for f, v in lst]
    with open(f'{OUT}/conflicts.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(['sku', 'file', 'navigableCategories', 'status']); w.writerows(conf)
    pairs, keep = set(), []
    for f in MAPS:
        for r in read(f):
            k = (r['master_id'], r['sku'], r.get('default_variant') or '', r.get('variant_type') or '')
            if k not in pairs: pairs.add(k); keep.append(k)
    with open(f'{OUT}/amp_map.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(['master_id', 'sku', 'default_variant', 'variant_type']); w.writerows(keep)
    with open('reports/links_to_add.csv', encoding='utf-8-sig', newline='') as a, open(f'{OUT}/approved_links.csv', 'w', encoding='utf-8-sig', newline='') as b:
        b.write(a.read())
    print(f'navcats.csv: {len(rec)} SKUs, status', dict(C.Counter(v[1] for v in rec.values())))
    print(f'conflicts.csv: {len({c[0] for c in conf})} SKUs where the files disagree  |  amp_map.csv: {len(keep)} rows  |  approved_links.csv copied')

if __name__ == '__main__': main()