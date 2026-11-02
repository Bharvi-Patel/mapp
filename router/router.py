#!/usr/bin/env python3
"""router.py - one file to run the whole catalog from ONE fetched navcats file. No rule or mapping code is changed:
this only calls the existing steps (cascade.py shadow -> rollup_products.py -> rollup_variations.py) in order.
Run it from the router folder, like the other scripts.

  1. Merge the many fetched files into the ONE navcats file (first file listed wins per SKU; a failed fetch never beats an ok record):
       python router.py navcats navcats_kits.csv pim_vendor_api_ingestion_202610290943.csv navcats_beds.csv --out navcats.csv

  2. Products (routes every raw item in the dump, then rolls up to products):
       python router.py products --dump onebuilddemo_for_router.sql --navcats navcats.csv --db reports/shadow.db --out reports/product_rollup.csv
     Any other flag is handed to rollup_products.py unchanged, e.g.
       --amp-map amp_map.csv  --approved-links approved_links.csv  --follow-navcats-amp  --pieces-fallback  --profile onebuild

  3. Variations (every variation takes its product's categories; the variations export from DBeaver is the one input the dump does not hold):
       python router.py variations --variations reports/variations.csv --products reports/product_rollup.csv --db reports/shadow.db --out reports/variation_rollup.csv

  4. Both in one go:  python router.py all <the products flags> --variations reports/variations.csv --variations-out reports/variation_rollup.csv

The router only reads the dump and the files you give it and writes CSVs (plus the local sqlite file given by --db). Nothing is written to any store database."""
import argparse, collections as C, csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
try: csv.field_size_limit(2**31 - 1)           # sys.maxsize overflows on Windows
except OverflowError: csv.field_size_limit(2**30)


def _read(path):
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, newline='', encoding=enc) as f: return list(csv.DictReader(f))
        except UnicodeDecodeError: continue
    raise SystemExit(f'cannot read {path}')


def merge_navcats(files, out):
    """Same rule as build_onebuild_inputs.py: per SKU the FIRST file that has it supplies the record, except that a failed fetch never beats an ok record."""
    rec, seen = {}, C.defaultdict(list)
    for f in files:
        for r in _read(f):
            sku = (r.get('sku') or '').strip()
            if not sku: continue
            row = (r.get('navigableCategories') or '', (r.get('status') or 'ok').strip())
            seen[sku].append((f, row))
            if sku not in rec or (rec[sku][1] != 'ok' and row[1] == 'ok'): rec[sku] = row
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(['sku', 'navigableCategories', 'status'])
        for sku in sorted(rec): w.writerow([sku, rec[sku][0], rec[sku][1]])
    conf = [(sku, f, v[0], v[1]) for sku, lst in seen.items() if len({v for _, v in lst}) > 1 for f, v in lst]
    cpath = os.path.splitext(out)[0] + '_conflicts.csv'
    with open(cpath, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(['sku', 'file', 'navigableCategories', 'status']); w.writerows(conf)
    print(f'{out}: {len(rec)} SKUs from {len(files)} files, status', dict(C.Counter(v[1] for v in rec.values())))
    print(f'{cpath}: {len({c[0] for c in conf})} SKUs where the files disagree (the first file listed was used; read this file)')


def _call(main, argv):
    """Run an existing script's main() with the given command line, exactly as if typed."""
    old = sys.argv
    sys.argv = [old[0]] + [str(x) for x in argv]
    try: main()
    finally: sys.argv = old


def run_products(a, extra):
    import cascade, rollup_products
    print(f'== step 1: route every raw item in {a.dump} (shadow, nothing applied) ==', flush=True)
    shadow = ['shadow', '--dump', a.dump, '--navcats', a.navcats, '--trust-vendor-path', '--all', '--db', 'sqlite:' + a.db]
    if a.vendor: shadow += ['--vendor', a.vendor]
    _call(cascade.main, shadow)
    print('\n== step 2: roll the decisions up to products ==', flush=True)
    roll = ['--navcats', a.navcats, '--dump', a.dump, '--db', a.db, '--out', a.out]
    if a.vendor: roll += ['--vendor', a.vendor]
    _call(rollup_products.main, roll + extra)


def run_variations(a):
    import rollup_variations
    print('\n== variations: every variation takes its product\'s categories ==', flush=True)
    _call(rollup_variations.main, ['--variations', a.variations, '--rollup', a.products, '--db', a.db, '--out', a.out])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    n = sub.add_parser('navcats', help='merge many fetched navcats files into ONE')
    n.add_argument('files', nargs='+'); n.add_argument('--out', default='navcats.csv')

    def products_flags(p):
        p.add_argument('--dump', default=os.path.join(HERE, 'dump_for_evidence.sql'))
        p.add_argument('--navcats', required=True, help='the ONE navcats file (sku, navigableCategories, status)')
        p.add_argument('--db', default='reports/shadow.db', help='local sqlite file the routing decisions are written to')
        p.add_argument('--vendor', default=None, help='default: the same vendors/ashley.yaml the other scripts use')
        p.add_argument('--out', default='reports/product_rollup.csv')

    pr = sub.add_parser('products', help='route everything, roll up to products'); products_flags(pr)

    v = sub.add_parser('variations', help='give every variation its product\'s categories')
    v.add_argument('--variations', default='reports/variations.csv', help='DBeaver export: uuid, product_id, sku, name')
    v.add_argument('--products', default='reports/product_rollup.csv', help='the products result')
    v.add_argument('--db', default='reports/shadow.db'); v.add_argument('--out', default='reports/variation_rollup.csv')

    al = sub.add_parser('all', help='products, then variations'); products_flags(al)
    al.add_argument('--variations', required=True); al.add_argument('--variations-out', default='reports/variation_rollup.csv')

    a, extra = ap.parse_known_args()
    if a.cmd != 'products' and a.cmd != 'all' and extra: ap.error('unrecognised arguments: ' + ' '.join(extra))
    if a.cmd == 'navcats': merge_navcats(a.files, a.out)
    elif a.cmd == 'products': run_products(a, extra)
    elif a.cmd == 'variations': run_variations(a)
    else:
        run_products(a, extra)
        run_variations(argparse.Namespace(variations=a.variations, products=a.out, db=a.db, out=a.variations_out))


if __name__ == '__main__':
    main()
