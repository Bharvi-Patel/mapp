"""List what the item-class rule decided. Run from the router folder: python -m check_icm_rows"""
import sqlite3, collections as C
from dumpreader import rows

dec = {s: slug for s, slug in sqlite3.connect('reports/shadow.db').execute(
    "select sku, primary_slug from router_decisions where rule='item_class_map' and status in ('shadow','applied')")}
info = {r['sku']: (r['itemName'], (r['itemClass'] or '').strip()) for r in rows('dump_for_evidence.sql', 'pim_raw_items') if r['sku'] in dec}
by = C.defaultdict(list)
for s, slug in dec.items(): by[(info[s][1], slug)].append(info[s][0])
print(len(dec), 'products decided by item_class_map')
for (cls, slug), names in sorted(by.items(), key=lambda x: -len(x[1])):
    print(f'\n{len(names):3d}  {cls}  ->  {slug}')
    for n in names[:12]: print('       ', n)