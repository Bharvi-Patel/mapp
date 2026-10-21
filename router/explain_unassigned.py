"""Explain WHY each unassigned product (review or conflict) is stuck, by linking it to its raw items.
Run from the router folder, after rollup_products.py:
    python explain_unassigned.py [--dump dump_for_evidence.sql] [--db reports/shadow.db]
                                 [--rollup reports/product_rollup.csv] [--out reports/unassigned_explained.csv]
Writes one row per unassigned product and prints the products grouped by (item_code, candidate categories)."""
import argparse, csv, json, os, sqlite3, collections as C
from dumpreader import rows

ap = argparse.ArgumentParser()
ap.add_argument('--dump', default='dump_for_evidence.sql')
ap.add_argument('--db', default='reports/shadow.db')
ap.add_argument('--rollup', default='reports/product_rollup.csv')
ap.add_argument('--out', default='reports/unassigned_explained.csv')
a = ap.parse_args()

with open(a.rollup, newline='', encoding='utf-8-sig') as f:
    unassigned = {r['product']: r for r in csv.DictReader(f) if r['state'] in ('review', 'conflict')}
print(f'{len(unassigned)} unassigned products in {a.rollup}')

raw = {r['uuid']: r for r in rows(a.dump, 'pim_raw_items')}
prod_name = {p['uuid']: (p.get('name') or p.get('title') or '') for p in rows(a.dump, 'pim_products')}
items_of = C.defaultdict(list)
for r in rows(a.dump, 'pim_product_raw_items'):
    if r['product_id'] in unassigned:
        items_of[r['product_id']].append(r['raw_item_id'])

queue = {}
for uuid, reason, cands in sqlite3.connect(a.db).execute(
        'select subject_uuid, reason, candidates from router_review_queue'):
    queue[uuid] = (reason, [x['slug'] for x in json.loads(cands or '[]')])

out = []
for p, u in unassigned.items():
    items = items_of.get(p, [])
    stuck = [i for i in items if i in queue]
    reasons = sorted({queue[i][0] for i in stuck})
    cands = sorted({s for i in stuck for s in queue[i][1]})
    if not cands and u['state'] == 'conflict':
        cands = sorted(u['category'].split(' | '))
    names = sorted({(raw[i]['itemName'] or '').strip() for i in stuck if i in raw})
    classes = sorted({(raw[i]['itemClass'] or '').strip() for i in items if i in raw})
    out.append(dict(
        product=p, product_name=prod_name.get(p, ''), state=u['state'], item_code=u['item_code'],
        n_raw_items=u['n_raw_items'], n_stuck_items=len(stuck), reasons=' | '.join(reasons),
        candidates=' | '.join(cands) or '(none)', stuck_item_names='; '.join(names[:6]),
        item_classes=' | '.join(classes), current_links=u['current']))

out.sort(key=lambda d: (d['candidates'], d['item_code'], d['product']))
os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)

n = len(out)
print(f'\nunassigned products grouped by item code + candidate categories ({n} total):')
g = C.Counter((d['item_code'] or '(blank)', d['candidates']) for d in out)
for (code, cands), k in g.most_common(20):
    print(f'{k:4d}  {100*k/n:5.1f}%  {code:20s} {cands[:110]}')
print('\nreasons:', dict(C.Counter(d['reasons'] or '(conflict, not from review queue)' for d in out)))
print(f'wrote {a.out}')