#!/usr/bin/env python3
"""Export the router's shadow decisions to a CSV: which product went to which category, by which rule.

  python export_decisions.py --db reports/shadow_all_trust.db --out reports/decisions.csv [--dump dump_for_evidence.sql]

Columns: sku, name (only with --dump), outcome (assigned / review), category (primary_slug), stage, rule, confidence,
review_reason (review rows), candidates (shortlist / top model picks). Only live rows (status 'shadow' or 'applied')."""
import argparse, csv, json, sqlite3

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True, help='the sqlite file shadow wrote, e.g. reports/shadow_all_trust.db')
    ap.add_argument('--out', default='reports/decisions.csv')
    ap.add_argument('--dump', help='optional: the SQL dump, to add product names')
    a = ap.parse_args()
    names = {}
    if a.dump:
        from dumpreader import rows
        names = {r['sku']: (r['itemFriendlyDesc'] or r['itemName'] or '').strip() for r in rows(a.dump, 'pim_raw_items') if not r['is_deleted']}
    conn = sqlite3.connect(a.db)
    q = """SELECT d.sku, d.outcome, d.primary_slug, d.stage, d.rule, d.confidence, r.reason, d.candidates
           FROM router_decisions d
           LEFT JOIN router_review_queue r ON r.decision_id = d.id
           WHERE d.status IN ('shadow','applied') ORDER BY d.outcome, d.rule, d.sku"""
    rows_out = conn.execute(q).fetchall()
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['sku'] + (['name'] if names else []) + ['outcome', 'category', 'stage', 'rule', 'confidence', 'review_reason', 'candidates'])
        for sku, outcome, slug, stage, rule, conf, reason, cands in rows_out:
            w.writerow([sku] + ([names.get(sku, '')] if names else []) + [outcome, slug or '', stage, rule, conf if conf is not None else '', reason or '', cands or ''])
    print(f'wrote {len(rows_out)} rows to {a.out}')

if __name__ == '__main__':
    main()