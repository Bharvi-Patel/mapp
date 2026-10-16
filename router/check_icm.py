"""Why did the item-class rule decide nothing? Run from the router folder: python check_icm.py"""
import sqlite3, collections as C
import cascade as CA

DUMP = 'dump_for_evidence.sql'
cfg = CA.K.load_vendor_config('vendors/ashley.yaml')
res = CA.resources_from_dump(cfg, DUMP, False)
print('config line present:', bool(cfg.get('item_class_map_file')), '| classes loaded into the router:', len(res.item_class_map))

q = [x[0] for x in sqlite3.connect('reports/shadow.db').execute('select sku from router_review_queue')]
nav = CA.load_navcats('navcats_merged.csv')
inputs = CA.inputs_from_dump(DUMP, set(q), cfg['vendor_id'], nav)
cnt = C.Counter(i.item_class for i in inputs.values())
hit = sum(n for c, n in cnt.items() if c in res.item_class_map)
print('review rows:', len(inputs), '| rows in a mapped class:', hit)
print('largest item classes in review:')
for c, n in cnt.most_common(12): print(f'  {n:4d}  {c}')