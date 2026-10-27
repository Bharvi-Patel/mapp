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
The response may be one product object or a list/wrapper holding products; the product whose 'sku' matches is used.

Second URL form: some SKUs return 204 (no content) from the path form above but data from the query form Postman uses,
  https://apigw3.ashleyfurniture.com/productinformation/Products?Environment=AFI&sku={sku}
When the first URL gives nothing, that form is tried. Set it with ASHLEY_API_URL_FALLBACK, or leave it unset and it is derived from
ASHLEY_API_URL (the {sku} moves from the path to a 'sku' query parameter; customer, Limit and Page are dropped)."""
import argparse, base64, concurrent.futures, csv, json, os, sys, time, urllib.error, urllib.parse, urllib.request

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
                if r.status == 204: return 204, '<204 no content>'                 # urlopen does not raise on 204
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

def fallback_url(url_t):
    """The query form (.../Products?Environment=AFI&sku={sku}) from the path form (.../Products/{sku}?...&customer=..&Limit=..&Page=..)."""
    env = os.environ.get('ASHLEY_API_URL_FALLBACK')
    if env: return env if '{sku}' in env else None
    u = urllib.parse.urlsplit(url_t)
    if '/{sku}' not in u.path: return None
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if k.lower() not in ('customer', 'limit', 'page', 'sku')]
    q = urllib.parse.urlencode(keep) + ('&' if keep else '') + 'sku={sku}'
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path.replace('/{sku}', ''), q, ''))

def read_skus(args):
    if args.skus_file:
        return [l.strip() for l in open(args.skus_file, encoding='utf-8') if l.strip()]
    keep = ('gold', 'gold_flagged', 'gold_ruled', 'rule_handled')
    with open(os.path.join(HERE, 'gold', 'gold.csv'), newline='', encoding='utf-8-sig') as f:
        return list(dict.fromkeys(r['sku'] for r in csv.DictReader(f) if r['status'] in keep and r['sku']))

def load_env():
    """Fill os.environ from a .env file in the repo root; values already set in the shell win."""
    p = os.path.join(HERE, '..', '.env')
    if not os.path.exists(p): return
    for line in open(p, encoding='utf-8-sig'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('\'"'))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--skus-file'); ap.add_argument('--out', default=os.path.join(HERE, 'navcats_gold.csv'))
    ap.add_argument('--delay', type=float, default=0.2, help='seconds between calls')
    ap.add_argument('--workers', type=int, default=1, help='requests in flight at once (default 1 = one at a time)')
    args = ap.parse_args()
    load_env()
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
    fb = fallback_url(url_t)
    print('fallback URL form:', fb.replace('{sku}', '<sku>') if fb else 'none')
    def lookup(sku):
        code, payload = fetch(url_t.format(sku=sku), headers)
        empty = code in (204, 404) or (code == 200 and (isinstance(payload, str) or not find_product(payload, sku)))
        if fb and empty:
            c2, p2 = fetch(fb.format(sku=sku), headers)
            if c2 == 200 and not isinstance(p2, str) and find_product(p2, sku): return c2, p2
        return code, payload
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
        def work(sku):
            r = lookup(sku); time.sleep(args.delay); return sku, r          # each worker pauses --delay after its call
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers))
        try:
            for i, (sku, (code, payload)) in enumerate(ex.map(work, skus), 1):   # results come back in SKU order; only this thread writes the file
                if code in (200, 204) and isinstance(payload, str):
                    row = [sku, '', 'bad_body']
                    print(f'  {sku}: HTTP {code} but there is no JSON body: {payload!r}')
                elif code == 200:
                    prod = find_product(payload, sku)
                    row = [sku, json.dumps(prod['navigableCategories']), 'ok'] if prod else [sku, '', 'no_field']
                else:
                    row = [sku, '', 'not_found' if code == 404 else f'error:{code}']
                    if code != 404:
                        bad += 1
                        if bad == 1: print(f'  first failure: {sku} -> HTTP {code}: {payload}')
                        if bad >= 3 and code in (401, 403, 0): w.writerow(row); sys.exit(f'Stopping after {bad} failures (HTTP {code}). Fix the cause and rerun; failed SKUs are retried.')
                if code in (200, 204): bad = 0
                if bad == 0 and code == 200 and row[2] == 'bad_body': pass
                w.writerow(row); f.flush()
                if i % 25 == 0: print(f'  {i}/{len(skus)}')
        finally:
            ex.shutdown(wait=False, cancel_futures=True)   # on Ctrl+C or an early stop, drop queued SKUs; only the few in flight finish
    print('done ->', args.out)

if __name__ == '__main__': main()