#!/usr/bin/env python3
"""Item-class map builder: which Ashley itemClass always lands in ONE of our categories.
Usage: python build_item_class_map.py [--min-agreement 100] [--min-items 3]
Reads evidence_out/pools.json (build_evidence.py), writes evidence_out/item_class_map.csv.
A class is kept when its top in-store leaf category holds at least min-agreement % of the class's items,
that category is strictly ahead of the runner-up, and the class has at least min-items items."""
import argparse, csv, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
EXCLUDED = ('component-skus', 'uncategorized', 'store-displays')
ap = argparse.ArgumentParser()
ap.add_argument('--pools', default=os.path.join(HERE, 'evidence_out', 'pools.json'))
ap.add_argument('--out', default=os.path.join(HERE, 'evidence_out', 'item_class_map.csv'))
ap.add_argument('--min-agreement', type=float, default=100)
ap.add_argument('--min-items', type=int, default=3)
ap.add_argument('--exclude', nargs='*', default=[], help='item classes to leave out, e.g. --exclude "RH BEDDING SDG DOM FOAM (D-MFG)"')
a = ap.parse_args()
SKIP = {x.strip() for x in a.exclude}

keep = []
for cls, p in json.load(open(a.pools, encoding='utf-8'))['pools'].items():
    if p.get('source') != 'links' or not p.get('items') or cls.strip() in SKIP: continue
    opts = sorted((o for o in p['options'] if o['in_store'] and not o['slug'].startswith(EXCLUDED)),
                  key=lambda o: -(o.get('support') or 0))
    if not opts: continue
    top = opts[0]; agree = 100 * (top.get('support') or 0) / p['items']
    runner = (opts[1].get('support') or 0) if len(opts) > 1 else 0
    if agree >= a.min_agreement and (top.get('support') or 0) > runner and p['items'] >= a.min_items:
        keep.append((cls.strip(), top['slug'], p['items'], top['support'], round(agree, 1)))
keep.sort(key=lambda r: -r[2])
with open(a.out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['item_class', 'slug', 'items', 'support', 'agreement_pct']); w.writerows(keep)
print(f'{len(keep)} item classes ({sum(r[2] for r in keep)} items) written to {a.out}')