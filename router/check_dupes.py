"""Do products with the same name get the same category? Run from the router folder: python check_dupes.py
Reads the dump (names) and reports/shadow.db (decisions). Changes nothing."""
import collections as C, re, sqlite3

def norm(s): return re.sub(r'\s+', ' ', str(s or '')).strip().lower()

def analyse(items, dec):
    """items: {sku: name}; dec: {sku: (outcome, slug)}. Returns (groups, inconsistent)."""
    groups = C.defaultdict(list)
    for sku, name in items.items():
        if norm(name): groups[norm(name)].append(sku)
    dups = {n: s for n, s in groups.items() if len(s) > 1}
    bad = {}
    for n, skus in dups.items():
        picks = {dec[s][1] for s in skus if s in dec and dec[s][0] == 'assigned'}
        if len(picks) > 1: bad[n] = [(s, dec.get(s)) for s in skus]
    return dups, bad

if __name__ == '__main__':
    from dumpreader import rows
    items = {r['sku']: r['itemName'] for r in rows('dump_for_evidence.sql', 'pim_raw_items') if not r['is_deleted'] and r['sku']}
    dec = {}
    for sku, slug, outcome in sqlite3.connect('reports/shadow.db').execute(
            "SELECT sku, primary_slug, outcome FROM router_decisions WHERE status IN ('shadow','applied') ORDER BY id"):
        dec[sku] = (outcome, slug)
    dups, bad = analyse(items, dec)
    print(len(items), 'raw items;', len(dups), 'names used by more than one SKU,', sum(len(v) for v in dups.values()), 'SKUs involved')
    print(len(bad), 'of those names were routed to different categories:')
    for n, lst in sorted(bad.items(), key=lambda x: -len(x[1]))[:15]:
        print(' ', n[:70])
        for s, d in lst[:4]: print('     ', s, d)