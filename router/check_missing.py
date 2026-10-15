"""Why are some golden SKUs missing from the shadow run? Run from the router folder:
python check_missing.py"""
import json, sqlite3
from dumpreader import rows

gold = {json.loads(l)['sku'] for l in open('golden.jsonl', encoding='utf-8-sig') if l.strip()}
run = {r[0] for r in sqlite3.connect('reports/shadow.db').execute('select sku from router_decisions')}
missing = sorted(gold - run)
raw = {r['sku']: r for r in rows('dump_for_evidence.sql', 'pim_raw_items')}
in_raw = [s for s in missing if s in raw]
deleted = [s for s in in_raw if raw[s]['is_deleted']]
print(len(missing), 'golden SKUs not in the run')
print(' ', len(in_raw), 'exist in pim_raw_items,', len(deleted), 'of those are marked deleted')
print(' ', len(missing) - len(in_raw), 'are not in pim_raw_items at all')
print('first 10 missing:', missing[:10])

# Do the missing SKUs exist in the product tables instead?
for table in ('pim_products', 'products'):
    try:
        skus = {r.get('sku') for r in rows('dump_for_evidence.sql', table)}
        print(f'{table}: {len([s for s in missing if s in skus])} of the {len(missing)} missing SKUs found')
    except Exception as e:
        print(f'{table}: could not read ({type(e).__name__}: {e})')