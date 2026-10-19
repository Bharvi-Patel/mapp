#!/usr/bin/env python3
"""List categories.

  python list_categories.py --db reports/shadow_all_trust.db      categories the router assigned, with product counts
  python list_categories.py --dump dump_for_evidence.sql          every leaf category that is in the store (what the router may assign)
Add --out file.csv to save the list."""
import argparse, csv, sqlite3, sys

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db'); ap.add_argument('--dump'); ap.add_argument('--out')
    a = ap.parse_args()
    if not (a.db or a.dump): ap.error('give --db and/or --dump')
    if a.db:
        conn = sqlite3.connect(a.db)
        res = conn.execute("SELECT primary_slug, COUNT(*) FROM router_decisions WHERE status IN ('shadow','applied') AND outcome='assigned' "
                           "GROUP BY primary_slug ORDER BY COUNT(*) DESC").fetchall()
        head, data = ['category', 'products'], res
    else:
        from dumpreader import rows
        pc = [c for c in rows(a.dump, 'pim_categories') if not c['deleted_at']]
        live = [c for c in pc if c['enabled'] == 1]
        parents = {str(c['parent_id']) for c in live}
        leaf = {c['slug'] for c in live if str(c['id']) not in parents}
        store = {c['slug'] for c in rows(a.dump, 'categories') if not c['deleted_at']}
        head, data = ['leaf_category_in_store'], [(s,) for s in sorted(leaf & store)]
    if a.out:
        with open(a.out, 'w', newline='', encoding='utf-8-sig') as f: w = csv.writer(f); w.writerow(head); w.writerows(data)
        print(f'wrote {len(data)} rows to {a.out}')
    else:
        for r in data: print('\t'.join(str(x) for x in r))
        print(f'-- {len(data)} categories', file=sys.stderr)

if __name__ == '__main__':
    main()