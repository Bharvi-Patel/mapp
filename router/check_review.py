import csv, sqlite3, collections as C

n = {}
with open('navcats_merged.csv', newline='', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        n[r['sku']] = r

q = [x[0] for x in sqlite3.connect('reports/shadow.db').execute("select distinct sku from router_decisions where status='shadow' and outcome='review'")]
print('review rows:', len(q))
print(C.Counter(n[s]['status'] if s in n else 'not_fetched' for s in q))
has = [s for s in q if s in n and n[s]['status'] == 'ok' and n[s]['navigableCategories'] not in ('', '[]')]
print('has an Ashley path:', len(has))