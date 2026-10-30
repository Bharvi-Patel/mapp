"""Which dump do a shadow database's decisions belong to?
usage: python check_db_vs_dump.py reports/shadow_fresh.db dump_for_evidence.sql onebuilddemo_for_router.sql
Prints, for the raw-item decisions in the database, how many uuids exist in each dump (read-only)."""
import sys, sqlite3
from dumpreader import rows
db, dumps = sys.argv[1], sys.argv[2:]
conn = sqlite3.connect(db)
dec = [(r[0], r[1], r[2]) for r in conn.execute(
    "select subject_uuid, sku, status from router_decisions where subject_type='raw_item' and status in ('shadow','applied')")]
print(f'{db}: {len(dec)} raw-item decisions')
raw = {}
for d in dumps:
    raw[d] = {(r.get('uuid') or r['id']): r.get('sku') for r in rows(d, 'pim_raw_items')}
    print(f'  {d}: {len(raw[d])} raw items')
names = list(raw)
from collections import Counter
c = Counter()
ex = {}
for u, sku, st in dec:
    key = tuple(n for n in names if u in raw[n]) or ('in no dump',)
    c[key] += 1
    ex.setdefault(key, []).append(sku)
for k, v in c.most_common():
    print(f'  uuid found in {" + ".join(k)}: {v}   e.g. {ex[k][:4]}')
for n in names:
    have = {u for u, _, _ in dec}
    miss = [s for u, s in raw[n].items() if u not in have]
    print(f'  raw items of {n} with NO decision in this database: {len(miss)}   e.g. {miss[:5]}')