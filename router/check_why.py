import sqlite3, collections as C
import cascade as CA

DUMP = 'dump_for_evidence.sql'
cfg = CA.K.load_vendor_config('vendors/ashley.yaml')
res = CA.resources_from_dump(cfg, DUMP, False)
nav = CA.load_navcats('navcats_merged.csv')

q = [x[0] for x in sqlite3.connect('reports/shadow.db').execute("select distinct sku from router_decisions where status='shadow' and outcome='review'")]
inputs = CA.inputs_from_dump(DUMP, set(q), cfg['vendor_id'], nav)

why = C.Counter()
for inp in inputs.values():
    why[(CA.undecided_why(inp, res), inp.item_type)] += 1

print('review products found:', len(inputs))
for (reason, itype), n in why.most_common():
    print(f'{n:5d}  {reason:30s} {itype}')