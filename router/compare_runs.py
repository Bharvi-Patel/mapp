"""Read-only. Which rule handled, in run B, the SKUs that went to review in run A?
usage (from router\\):  python compare_runs.py reports/demo_test.db reports/demo_test2.db"""
import sqlite3, sys, collections as C
a, b = (sqlite3.connect(p) for p in sys.argv[1:3])
rev = {s for (s,) in a.execute("select sku from router_decisions where status='shadow' and outcome='review'")}
rule_b = dict(b.execute("select sku, rule from router_decisions where status='shadow'"))
print(f"review in run A: {len(rev)}")
print("what run B did with those SKUs:")
for rule, n in C.Counter(rule_b.get(s, 'not in run B') for s in rev).most_common(): print(f"  {n:5d}  {rule}")
