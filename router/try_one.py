import fetch_navcats as f, os, base64, time
f.load_env()
cred = f"{os.environ['ASHLEY_API_USER']}:{os.environ['ASHLEY_API_PASSWORD']}".encode()
h = {'Authorization': 'Basic ' + base64.b64encode(cred).decode(), 'Accept': 'application/json'}
if os.environ.get('ASHLEY_CLIENT_ID'): h['client_id'] = os.environ['ASHLEY_CLIENT_ID']
u = os.environ['ASHLEY_API_URL']
for name, url in (('path', u), ('query', f.fallback_url(u))):
    t = time.time()
    code, body = f.fetch(url.format(sku='B200-96'), h, retries=1)
    print(name, code, round(time.time() - t, 1), 's', str(body)[:150])