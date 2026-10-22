"""Look inside one Ashley response and show where (and whether) a SKU's navigableCategories sits. Same ASHLEY_* variables as fetch_navcats.py.
Set ASHLEY_API_URL to the form that returned data, e.g.
  $env:ASHLEY_API_URL = 'https://apigw3.ashleyfurniture.com/productinformation/Products?Environment=AFI&sku={sku}'
  python inspect_navcats.py M12011
Prints the response shape, how many products it holds and which SKUs, and every place the SKU appears with its key name. No credentials are printed."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from debug_navcats import base_headers
import urllib.request

def walk(x, path=''):
    """Yield (path, dict) for every dict inside x."""
    if isinstance(x, dict):
        yield path or '$', x
        for k, v in x.items(): yield from walk(v, f'{path}.{k}' if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x[:2000]): yield from walk(v, f'{path}[{i}]')

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    sku, tpl = sys.argv[1], os.environ.get('ASHLEY_API_URL', '')
    if '{sku}' not in tpl: sys.exit('Set ASHLEY_API_URL (containing {sku}) first.')
    with urllib.request.urlopen(urllib.request.Request(tpl.format(sku=sku), headers=base_headers()), timeout=60) as r: data = json.loads(r.read().decode('utf-8', 'replace'))
    print('top level:', type(data).__name__, (list(data)[:10] if isinstance(data, dict) else f'{len(data)} items'))
    if isinstance(data, dict):
        for k in ('metadata', 'links'):
            if k in data: print(f'{k}:', json.dumps(data[k])[:700])
        for k, v in data.items():
            if isinstance(v, list): print(f'{k}: list of {len(v)}')
    dicts = list(walk(data))
    with_sku = [(p, d) for p, d in dicts if 'sku' in d or 'SKU' in d or 'Sku' in d]
    print(f'{len(dicts)} objects inside; {len(with_sku)} have a sku-like key')
    skus = [str(d.get('sku', d.get('SKU', d.get('Sku')))) for _, d in with_sku]
    print('first SKUs:', skus[:8], '| distinct:', len(set(skus)))
    nav = [(p, d) for p, d in dicts if 'navigableCategories' in d]
    print(f'{len(nav)} objects have navigableCategories; first keys of one:', (list(nav[0][1])[:12] if nav else 'n/a'))
    hits = [(p, d) for p, d in dicts if any(str(v).strip().upper() == sku.upper() for v in d.values() if isinstance(v, (str, int)))]
    print(f'\nobjects where some field equals {sku}: {len(hits)}')
    for p, d in hits[:5]:
        keys = [k for k, v in d.items() if isinstance(v, (str, int)) and str(v).strip().upper() == sku.upper()]
        print(f'  at {p}: matching field(s) {keys}; object keys {list(d)[:12]}; has navigableCategories: {"navigableCategories" in d}')
        if 'navigableCategories' in d: print('    navigableCategories =', json.dumps(d['navigableCategories'])[:300])

if __name__ == '__main__': main()