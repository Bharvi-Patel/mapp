import sqlite3, collections as C
import cascade as CA

DUMP = 'dump_for_evidence.sql'
cfg = CA.K.load_vendor_config('vendors/ashley.yaml')
res = CA.resources_from_dump(cfg, DUMP, False)
nav = CA.load_navcats('navcats_merged.csv')
q = [x[0] for x in sqlite3.connect('reports/shadow.db').execute('select sku from router_review_queue')]
inputs = CA.inputs_from_dump(DUMP, set(q), cfg['vendor_id'], nav)

c, names = C.Counter(), C.defaultdict(list)
for inp in inputs.values():
    if CA.undecided_why(inp, res) != 'component_or_excluded_only':
        continue
    slugs = dict.fromkeys(res.code_slug.get(x, x) for x in (inp.vendor_category_path or []))
    ex = tuple(sorted(s for s in slugs if s in res.leaf and s in res.excluded))
    c[ex] += 1
    if len(names[ex]) < 6:
        names[ex].append(inp.name)

for ex, n in c.most_common(10):
    print(n, ex)
    for nm in names[ex]:
        print('     ', nm)
        