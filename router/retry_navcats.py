"""Retry the SKUs whose navigableCategories fetch failed (bad_body, no_field, error:*), then merge the answers back.
fetch_navcats.py never retries bad_body / no_field rows (it treats them as done), so retry them into a separate file:

  python retry_navcats.py list                      -> failed_skus.txt (every SKU in navcats_merged.csv whose status is not ok)
  python fetch_navcats.py --skus-file failed_skus.txt --out navcats_retry.csv     (same ASHLEY_* environment variables as before)
  python retry_navcats.py merge                     -> navcats_merged.csv updated in place (a backup is kept as navcats_merged.bak.csv)
Only rows that come back 'ok' replace the old ones; anything still failing stays as it was."""
import csv, shutil, sys

MERGED, RETRY, SKUS, BACKUP = 'navcats_merged.csv', 'navcats_retry.csv', 'failed_skus.txt', 'navcats_merged.bak.csv'
FIELDS = ['sku', 'navigableCategories', 'status']

def read(path):
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, newline='', encoding=enc) as f: return list(csv.DictReader(f))
        except UnicodeDecodeError: continue

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    rows = read(MERGED)
    if cmd == 'list':
        failed = [r['sku'] for r in rows if (r.get('status') or '').strip() != 'ok']
        open(SKUS, 'w', encoding='utf-8').write('\n'.join(failed) + '\n')
        print(f'{len(failed)} failed SKUs of {len(rows)} -> {SKUS}')
    elif cmd == 'merge':
        got = {r['sku']: r for r in read(RETRY) if (r.get('status') or '').strip() == 'ok'}
        shutil.copyfile(MERGED, BACKUP)
        out = [got.get(r['sku'], r) for r in rows]
        with open(MERGED, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f); w.writerow(FIELDS); w.writerows([r['sku'], r['navigableCategories'], r['status']] for r in out)
        still = sum(1 for r in out if (r.get('status') or '').strip() != 'ok')
        print(f'{len(got)} SKUs recovered; {still} still failing. Backup: {BACKUP}')
    else:
        sys.exit(__doc__)

if __name__ == '__main__': main()