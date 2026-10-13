#!/usr/bin/env python3
"""Export Ashley navigableCategories per SKU, so the cascade can be scored on real vendor paths.

  export ASHLEY_API_URL='https://apigw3.ashleyfurniture.com/productinformation/Products/{sku}?Environment=AFI&customer=<your customer no>&Limit=1000&Page=1'
  export ASHLEY_API_USER='...'  ASHLEY_API_PASSWORD='...'   # HTTP Basic, as in the Postman 'Products api' request; never commit these
  export ASHLEY_CLIENT_ID='...'     # subscription key, sent as the 'client_id' header (the gateway asks for it; see Postman Headers tab)
  # (header name can be changed with ASHLEY_CLIENT_ID_HEADER)
  # or, for a bearer token instead: ASHLEY_API_TOKEN (optional ASHLEY_AUTH_HEADER, ASHLEY_AUTH_PREFIX)
  python fetch_navcats.py                    # the answer-key SKUs in gold/gold.csv
  python fetch_navcats.py --skus-file all_skus.txt --out navcats_all.csv
  python cascade.py eval --navcats navcats_gold.csv --trust-vendor-path

Output CSV: sku, navigableCategories (JSON list as the API returned it), status (ok | not_found | no_field | error:<code>).
Resumable: SKUs already in the output file are skipped, so a rerun after a failure continues where it stopped.
The response may be one product object or a list/wrapper holding products; the product whose 'sku' matches is used."""
import argparse, base64, csv, json, os, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

def find_product(payload, sku):
    """Depth-first search for the dict whose sku equals `sku` and which carries navigableCategories."""
    stack = [payload]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if str(x.get('sku', '')).strip().upper() == sku.upper() and 'navigableCategories' in x: return x
            stack.extend(x.values())
        elif isinstance(x, list): stack.extend(x)
    return None

def fetch(url, headers, retries=5):
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode('utf-8', 'replace')
            try: return 200, json.loads(text)
            except ValueError: return 200, text[:200] or '<empty body>'       # 200 but not JSON: recorded as bad_body
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = int(e.headers.get('Retry-After') or 0) or 2 ** attempt
                time.sleep(wait); continue
            try: body = e.read().decode('utf-8', 'replace')[:300]
            except Exception: body = ''
            return e.code, f"{body} | WWW-Authenticate: {e.headers.get('WWW-Authenticate')}"
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1: time.sleep(2 ** attempt); continue
            return 0, str(e)

def read_skus(args):
    if args.skus_file:
        return [l.strip() for l in open(args.skus_file, encoding='utf-8') if l.strip()]
    keep = ('gold', 'gold_flagged', 'gold_ruled', 'rule_handled')
    with open(os.path.join(HERE, 'gold', 'gold.csv'), newline='', encoding='utf-8-sig') as f:
        return list(dict.fromkeys(r['sku'] for r in csv.DictReader(f) if r['status'] in keep and r['sku']))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--skus-file'); ap.add_argument('--out', default=os.path.join(HERE, 'navcats_gold.csv'))
    ap.add_argument('--delay', type=float, default=0.2, help='seconds between calls')
    args = ap.parse_args()
    url_t, token = os.environ.get('ASHLEY_API_URL'), os.environ.get('ASHLEY_API_TOKEN')
    user, pw = os.environ.get('ASHLEY_API_USER'), os.environ.get('ASHLEY_API_PASSWORD')
    if not url_t or '{sku}' not in url_t or not (token or (user and pw)):
        sys.exit('Set ASHLEY_API_URL (containing {sku}) and either ASHLEY_API_USER + ASHLEY_API_PASSWORD or ASHLEY_API_TOKEN. See the top of this file.')
    if user and pw:
        headers = {'Authorization': 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode(), 'Accept': 'application/json'}
    else:
        headers = {os.environ.get('ASHLEY_AUTH_HEADER', 'Authorization'): os.environ.get('ASHLEY_AUTH_PREFIX', 'Bearer ') + token,
                   'Accept': 'application/json'}
    cid = os.environ.get('ASHLEY_CLIENT_ID')
    if cid: headers[os.environ.get('ASHLEY_CLIENT_ID_HEADER', 'client_id')] = cid
    done = set(); kept = []
    if os.path.exists(args.out):
        with open(args.out, newline='', encoding='utf-8') as f:
            kept = [r for r in csv.DictReader(f) if r['status'] in ('ok', 'not_found', 'no_field', 'bad_body')]   # error rows are retried
        done = {r['sku'] for r in kept}
        with open(args.out, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f); w.writerow(['sku', 'navigableCategories', 'status'])
            w.writerows([r['sku'], r['navigableCategories'], r['status']] for r in kept)
    skus = [s for s in read_skus(args) if s not in done]
    print(f'{len(skus)} SKUs to fetch ({len(done)} already in {args.out})')
    new = not os.path.exists(args.out); bad = 0
    with open(args.out, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if new: w.writerow(['sku', 'navigableCategories', 'status'])
        for i, sku in enumerate(skus, 1):
            code, payload = fetch(url_t.format(sku=sku), headers)
            if code == 200 and isinstance(payload, str):
                row = [sku, '', 'bad_body']
                print(f'  {sku}: HTTP 200 but the body is not JSON: {payload!r}')
            elif code == 200:
                prod = find_product(payload, sku)
                row = [sku, json.dumps(prod['navigableCategories']), 'ok'] if prod else [sku, '', 'no_field']
            else:
                row = [sku, '', 'not_found' if code == 404 else f'error:{code}']
                if code != 404:
                    bad += 1
                    if bad == 1: print(f'  first failure: {sku} -> HTTP {code}: {payload}')
                    if bad >= 3 and code in (401, 403, 0): w.writerow(row); sys.exit(f'Stopping after {bad} failures (HTTP {code}). Fix the cause and rerun; failed SKUs are retried.')
            if code == 200: bad = 0
            if bad == 0 and code == 200 and row[2] == 'bad_body': pass
            w.writerow(row); f.flush()
            if i % 25 == 0: print(f'  {i}/{len(skus)}')
            time.sleep(args.delay)
    print('done ->', args.out)

if __name__ == '__main__': main()