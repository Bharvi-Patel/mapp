"""Score the router's shadow decisions against the other team's golden.jsonl.
Usage (from the router folder):  python score_golden.py golden.jsonl reports/shadow.db
Reads router_decisions only; writes reports/golden_disagreements.csv. Changes nothing else."""
import csv, json, sqlite3, sys, collections as C, os

gpath = sys.argv[1] if len(sys.argv) > 1 else 'golden.jsonl'
dpath = sys.argv[2] if len(sys.argv) > 2 else 'reports/shadow.db'

gold = {}
with open(gpath, encoding='utf-8-sig') as f:
    for line in f:
        if line.strip():
            r = json.loads(line); gold[r['sku']] = r['accept']

dec = {}
_conn = sqlite3.connect(dpath)
try: _rows = _conn.execute("SELECT sku, primary_slug, outcome, rule, slugs FROM router_decisions WHERE status IN ('shadow','applied') ORDER BY id").fetchall()
except sqlite3.OperationalError: _rows = [r + (None,) for r in _conn.execute("SELECT sku, primary_slug, outcome, rule FROM router_decisions WHERE status IN ('shadow','applied') ORDER BY id")]
class Pick(str):                              # the primary slug, carrying every slug of a multi-category decision
    slugs = ()
for sku, slug, outcome, rule, slugs in _rows:
    p = Pick(slug or ''); p.slugs = tuple(json.loads(slugs)) if slugs else ((slug,) if slug else ())
    dec[sku] = (p, outcome, rule)             # later rows overwrite earlier ones

found = [s for s in gold if s in dec]
asg = [s for s in found if dec[s][1] == 'assigned']
rev = [s for s in found if dec[s][1] == 'review']
unc = [s for s in found if dec[s][1] == 'uncategorized']
hit = [s for s in asg if set(dec[s][0].slugs) & set(gold[s])]          # right when ANY of its categories is an accepted answer
miss = [s for s in asg if not set(dec[s][0].slugs) & set(gold[s])]
single = [s for s in asg if len(gold[s]) == 1]
single_hit = [s for s in single if set(dec[s][0].slugs) & set(gold[s])]
first_hit = [s for s in asg if dec[s][0] == gold[s][0]]

def pct(a, b): return f'{100*a/b:.1f}%' if b else 'n/a'

print(f'golden rows: {len(gold)}   found in shadow run: {len(found)}   not in run: {len(gold)-len(found)}')
print(f'assigned by router: {len(asg)} ({pct(len(asg), len(found))})   sent to review: {len(rev)} ({pct(len(rev), len(found))})   uncategorized: {len(unc)}')
print()
print(f'Agree with golden (pick is any accepted answer): {len(hit)} of {len(asg)} assigned = {pct(len(hit), len(asg))}')
print(f'   same, counting review rows as not agreeing:   {len(hit)} of {len(found)} = {pct(len(hit), len(found))}')
print(f'Differ from golden: {len(miss)} ({pct(len(miss), len(asg))} of assigned)')
print(f'Rows with exactly one accepted answer: {len(single_hit)} of {len(single)} = {pct(len(single_hit), len(single))}')
print(f'Pick equals the first listed answer:   {len(first_hit)} of {len(asg)} = {pct(len(first_hit), len(asg))}')
print()
print('By rule (assigned rows):')
by = C.defaultdict(lambda: [0, 0])
for s in asg:
    by[dec[s][2]][1] += 1
    by[dec[s][2]][0] += bool(set(dec[s][0].slugs) & set(gold[s]))
for rule, (h, n) in sorted(by.items(), key=lambda x: -x[1][1]):
    print(f'  {rule:28s} {h:5d} of {n:5d} = {pct(h, n)}')
print()
why = dict(sqlite3.connect(dpath).execute("SELECT sku, reason FROM router_review_queue"))
print('Review reasons among golden rows:', dict(C.Counter(why.get(s, '?') for s in rev)))

os.makedirs('reports', exist_ok=True)
with open('reports/golden_disagreements.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f); w.writerow(['sku', 'rule', 'router_pick', 'golden_accept'])
    for s in miss: w.writerow([s, dec[s][2], dec[s][0], ' | '.join(gold[s])])
print(f'\nwrote reports/golden_disagreements.csv ({len(miss)} rows)')