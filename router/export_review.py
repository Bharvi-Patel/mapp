"""List the raw items still in review after the latest shadow run, with why, into reports/review_now.csv. Run from the router folder:
    python export_review.py
Columns: sku, name, item_type, item_code, item_class, why (same reasons as check_why.py), navcats_status (from navcats_merged.csv;
'not_in_file' if the SKU has no row), has_ashley_path, path_codes (the category codes the router had), product_uuid (the raw item's uuid)."""
import csv, sqlite3
import cascade as CA

DUMP, NAVCATS, DB, OUT = 'dump_for_evidence.sql', 'navcats_merged.csv', 'reports/shadow.db', 'reports/review_now.csv'
cfg = CA.K.load_vendor_config('vendors/ashley.yaml')
res = CA.resources_from_dump(cfg, DUMP, False)
nav = CA.load_navcats(NAVCATS)
status = {r['sku']: (r.get('status') or '').strip() for r in CA._csv_any(NAVCATS) if r.get('sku')}

skus = [x[0] for x in sqlite3.connect(DB).execute("select distinct sku from router_decisions where status='shadow' and outcome='review'")]
inputs = CA.inputs_from_dump(DUMP, set(skus), cfg['vendor_id'], nav)

rows = []
for inp in inputs.values():
    rows.append(dict(sku=inp.sku, name=inp.name, item_type=inp.item_type, item_code=inp.item_code, item_class=inp.item_class,
                     why=CA.undecided_why(inp, res), navcats_status=status.get(inp.sku, 'not_in_file'),
                     has_ashley_path=bool(nav.get(inp.sku)), path_codes=' | '.join(inp.vendor_category_path or []), uuid=inp.subject_uuid))
rows.sort(key=lambda r: (r['navcats_status'] == 'ok', r['why'], r['item_code'] or '', r['sku']))
with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f'{len(rows)} review items -> {OUT}')
by = {}
for r in rows: by.setdefault((r['navcats_status'], r['why'], r['item_type']), []).append(r['sku'])
for (st, why, it), s in sorted(by.items(), key=lambda kv: -len(kv[1])): print(f'{len(s):4d}  fetch={st:9s} {why:28s} {it:10s} e.g. {", ".join(s[:3])}')