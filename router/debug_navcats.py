"""Why does one SKU come back 'HTTP 200 but empty' in fetch_navcats.py while Postman returns data?
Sends the same request several ways and prints what each returns (status, body length, a few response headers, whether the SKU's
navigableCategories is in the body). Uses the same ASHLEY_* environment variables as fetch_navcats.py. Prints no credentials.

  python debug_navcats.py M12011

Variants: A = exactly what fetch_navcats.py sends; B = Postman-like headers (User-Agent PostmanRuntime, Accept */*, gzip);
A3 / B3 = the same request three times with a 3 s pause (some gateways answer empty on a cold first call)."""
import base64, gzip, json, os, sys, time, urllib.error, urllib.request, zlib

def base_headers():
    token, user, pw = os.environ.get('ASHLEY_API_TOKEN'), os.environ.get('ASHLEY_API_USER'), os.environ.get('ASHLEY_API_PASSWORD')
    if user and pw: h = {'Authorization': 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode(), 'Accept': 'application/json'}
    elif token: h = {os.environ.get('ASHLEY_AUTH_HEADER', 'Authorization'): os.environ.get('ASHLEY_AUTH_PREFIX', 'Bearer ') + token, 'Accept': 'application/json'}
    else: sys.exit('Set ASHLEY_API_USER + ASHLEY_API_PASSWORD (or ASHLEY_API_TOKEN) first.')
    cid = os.environ.get('ASHLEY_CLIENT_ID')
    if cid: h[os.environ.get('ASHLEY_CLIENT_ID_HEADER', 'client_id')] = cid
    return h

def call(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r: code, hd, body = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e: code, hd, body = e.code, e.headers, e.read()
    except Exception as e: return f'ERROR {type(e).__name__}: {e}'
    enc = (hd.get('Content-Encoding') or '').lower()
    try:
        if enc == 'gzip': body = gzip.decompress(body)
        elif enc == 'deflate': body = zlib.decompress(body)
    except Exception: pass
    text = body.decode('utf-8', 'replace')
    info = f'HTTP {code} | {len(body)} bytes | type={hd.get("Content-Type")} | encoding={enc or "-"} | transfer={hd.get("Transfer-Encoding") or "-"}'
    try: has = 'navigableCategories' in json.dumps(json.loads(text))
    except ValueError: has = False
    return info + f' | navigableCategories in body: {has}' + ('' if has else f' | body starts: {text[:120]!r}')

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    sku, tpl = sys.argv[1], os.environ.get('ASHLEY_API_URL', '')
    if '{sku}' not in tpl: sys.exit('Set ASHLEY_API_URL (containing {sku}) first.')
    url = tpl.format(sku=sku)
    A = base_headers()
    B = dict(A); B.update({'User-Agent': 'PostmanRuntime/7.43.0', 'Accept': '*/*', 'Accept-Encoding': 'gzip, deflate', 'Connection': 'keep-alive'})
    print(f'SKU {sku}\n')
    print('A  script headers      :', call(url, A))
    print('B  Postman-like headers:', call(url, B))
    for name, h in (('A3', A), ('B3', B)):
        for i in range(3):
            time.sleep(3); print(f'{name} try {i + 1} after 3 s     :', call(url, h))

if __name__ == '__main__': main()