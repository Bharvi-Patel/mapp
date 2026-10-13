#!/usr/bin/env python3
"""Answer key (gold set) tools: merge two labelers into one key, draw a human spot-check, score it.

  python gold.py build            merge labels_A + labels_B (+ vendor rules + gold/rulings.csv) -> gold/gold.csv
  python gold.py spot  [--n 60]   blind human spot-check sheet from the key       -> gold/spot_check.xlsx (+ .csv)
  python gold.py score FILE...    compare filled-in spot-check(s) (.xlsx or .csv) with the key; later files override earlier
  python gold.py redo FILE        sheet with only the rows where a person picked a non-leaf category -> gold/spot_check_redo.xlsx

Statuses in gold.csv:
  gold, gold_flagged   labelers agree (flagged = at least one said Unsure)          -> scored for the model
  gold_ruled           labelers split; a person/tie rule settled it                  -> scored for the model
  rule_handled         a vendor rule decides it (e.g. SKU prefix)                    -> scored for that rule, not the model
  hold_not_in_store    agreed category is not in the store yet                       -> excluded until the category sync runs
  review               labelers split and no rule applies                            -> a person decides (add it to gold/rulings.csv)
  excluded             contested; a ruling (slug __exclude__) leaves it out of scoring
gold_slug is '__none__' when no category fits (the router should send those to review)."""
import argparse, csv, math, os, random, re, sys
from copy import copy
import collections as C
import openpyxl, yaml
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
NONE = '__none__'
EXCLUDE = '__exclude__'     # in gold/rulings.csv: contested row, leave it out of scoring
KEY_COLS = ['row_id', 'sku', 'name', 'label_a', 'unsure_a', 'label_b', 'unsure_b',
            'status', 'gold_slug', 'rule', 'note']

def P(*a): return os.path.join(HERE, *a)

def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def read_sheet(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {}
    for r in wb['Label'].iter_rows(min_row=4, values_only=True):
        if r[0]:
            out[str(r[0])] = dict(row_id=str(r[0]), sku=str(r[1] or ''), name=str(r[2] or ''), description=str(r[4] or ''))
    return out

def read_leaf(path):
    return {r['slug']: r['in_store'] == 'True' for r in read_csv(path)}

def read_rulings(path):
    return {r['row_id']: r for r in read_csv(path)} if os.path.exists(path) else {}

def _m(slug, pat):
    return slug.startswith(pat) if pat.endswith('-') else slug == pat

def decide(sku, a, b, cfg, in_store, ruling=None):
    """a, b: {'slug':..., 'unsure': 'Y'|''}. Returns (status, gold_slug, rule, note)."""
    for prefix, slug in (cfg.get('sku_prefix_rules') or {}).items():
        if sku.startswith(prefix):
            return 'rule_handled', slug, 'sku_prefix:' + prefix, ''
    if ruling:
        slug = ruling['slug']
        if slug == EXCLUDE: return 'excluded', '', 'ruling', ruling.get('reason', '')
        status = 'hold_not_in_store' if in_store.get(slug) is False else 'gold_ruled'
        return status, slug, 'ruling', ruling.get('reason', '')
    sa, sb = a['slug'], b['slug']
    if sa != sb:
        for t in cfg.get('tie_prefer') or []:
            for x, y in ((sa, sb), (sb, sa)):
                if _m(x, t['prefer']) and _m(y, t['over']):
                    st = 'hold_not_in_store' if in_store.get(x) is False else 'gold_ruled'
                    return st, x, 'tie_prefer', f"{t['prefer']} over {t['over']}"
        return 'review', '', '', f'labelers split: {sa} vs {sb}'
    if in_store.get(sa) is False:
        return 'hold_not_in_store', sa, '', 'category not in the store yet'
    flagged = a['unsure'] == 'Y' or b['unsure'] == 'Y'
    return ('gold_flagged' if flagged else 'gold'), sa, '', ''

def wilson(k, n, z=1.96):
    if n == 0: return 0.0, 1.0
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d

def norm_slug(s):
    s = (s or '').strip()
    if not s: return ''
    if s.upper() == 'NONE FITS' or s == NONE: return NONE
    m = re.search(r'\[([^\]]+)\]\s*$', s)      # sheet dropdown text: "Name | path [slug]"
    return m.group(1) if m else s

def build(args):
    sheet = read_sheet(args.sheet)
    A = {r['row_id']: r for r in read_csv(args.a)}
    B = {r['row_id']: r for r in read_csv(args.b)}
    in_store = read_leaf(args.leaf)
    cfg = yaml.safe_load(open(args.vendor, encoding='utf-8'))
    rulings = read_rulings(args.rulings)
    problems = []
    if not (set(sheet) == set(A) == set(B)):
        problems.append(f'row ids differ: sheet {len(sheet)}, A {len(A)}, B {len(B)}')
    for name, L in (('A', A), ('B', B)):
        for i, r in L.items():
            s = r['slug']
            if s != NONE and s not in in_store and not any(s == v for v in (cfg.get('sku_prefix_rules') or {}).values()):
                problems.append(f'labeler {name} {i}: unknown slug {s}')
    for i, r in rulings.items():
        if r['slug'] not in (NONE, EXCLUDE) and r['slug'] not in in_store: problems.append(f'ruling {i}: unknown slug {r["slug"]}')
    if problems:
        print('\n'.join(problems)); sys.exit(1)
    rows = []
    for i in sorted(sheet):
        a = dict(slug=A[i]['slug'], unsure=A[i]['unsure']); b = dict(slug=B[i]['slug'], unsure=B[i]['unsure'])
        st, slug, rule, note = decide(sheet[i]['sku'], a, b, cfg, in_store, rulings.get(i))
        rows.append(dict(row_id=i, sku=sheet[i]['sku'], name=sheet[i]['name'], label_a=a['slug'], unsure_a=a['unsure'],
                         label_b=b['slug'], unsure_b=b['unsure'], status=st, gold_slug=slug, rule=rule, note=note))
    write_csv(os.path.join(args.out, 'gold.csv'), KEY_COLS, rows)
    cnt = C.Counter(r['status'] for r in rows)
    none = sum(1 for r in rows if r['gold_slug'] == NONE)
    lines = [f'# Answer key summary ({len(rows)} rows)', '', '| status | rows |', '|---|---|']
    lines += [f'| {k} | {v} |' for k, v in sorted(cnt.items())]
    lines += ['', f'Rows whose gold answer is "no category fits": {none}',
              f'Rule-handled by: {dict(C.Counter(r["rule"] for r in rows if r["status"] == "rule_handled"))}']
    for st in ('review', 'excluded', 'hold_not_in_store'):
        ids = [f"{r['row_id']} ({r['name'][:40]})" for r in rows if r['status'] == st]
        if ids: lines += ['', f'**{st}**: ' + '; '.join(ids)]
    open(os.path.join(args.out, 'summary.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))

ORDER = [1, 2, 3, 8, 9, 10, 4, 5, 6, 7]   # old column -> new position: answer columns right after the name
WIDTHS = dict(A=9, B=14, C=40, D=80, E=10, F=40, G=22, H=70, I=24, J=40)

def write_spot_xlsx(template, ids, path, leaf_slugs=None):
    """Copy the labeling sheet (same Categories dropdown), keep only the chosen rows, blank answers, and put
    'Your category' / 'Unsure' / 'Notes' right after the product name so the dropdown is never scrolled off screen."""
    wb = openpyxl.load_workbook(template); ws = wb['Label']; old_max = ws.max_row
    rownum = {str(ws.cell(r, 1).value): r for r in range(4, old_max + 1) if ws.cell(r, 1).value}
    snap = lambda r: [(ws.cell(r, c).value, copy(ws.cell(r, c)._style)) for c in range(1, 11)]
    header = snap(3); data = [snap(rownum[i]) for i in ids]
    cat_formula = next(dv.formula1 for dv in ws.data_validations.dataValidation if str(dv.sqref).startswith('H'))
    if leaf_slugs is not None:      # offer leaf categories only, so a person cannot pick a parent
        cs = wb['Categories']; n0 = cs.max_row
        entries = [cs.cell(r, 1).value for r in range(2, n0 + 1) if cs.cell(r, 1).value]
        slug_of = lambda t: (re.search(r'\[([^\]]+)\]\s*$', t) or [None, None])[1]
        kept = [t for t in entries if t == 'NONE FITS' or slug_of(t) in leaf_slugs]
        for r in range(2, n0 + 1): cs.cell(r, 1).value = None
        for k, t in enumerate(kept): cs.cell(2 + k, 1).value = t
        cat_formula = f'=Categories!$A$2:$A${1 + len(kept)}'
    def put(r, snapped, blank_answers):
        for new, old in enumerate(ORDER, 1):
            v, st = snapped[old - 1]
            cell = ws.cell(r, new); cell._style = copy(st)
            cell.value = None if (blank_answers and old >= 8) else v
    put(3, header, False)
    for k, snapped in enumerate(data): put(4 + k, snapped, True)
    last = 3 + len(ids)
    for r in range(last + 1, old_max + 1):
        for c in range(1, 11): ws.cell(r, c).value = None
    ws.delete_rows(last + 1, old_max - last)
    for col, w in WIDTHS.items(): ws.column_dimensions[col].width = w
    ws.data_validations.dataValidation = []
    dv1 = DataValidation(type='list', formula1=cat_formula, allow_blank=True); dv1.add(f'D4:D{last}')
    dv2 = DataValidation(type='list', formula1='"Y"', allow_blank=True); dv2.add(f'E4:E{last}')
    ws.add_data_validation(dv1); ws.add_data_validation(dv2)
    ws['B1'] = None
    wb['Read me']['A1'] = 'Category labeling spot-check'
    wb.save(path)

def read_human(path):
    """Filled-in spot-check as a list of {'row_id', 'human_slug'}; accepts .xlsx (Label sheet) or .csv."""
    if not path.lower().endswith('.xlsx'): return read_csv(path)
    ws = openpyxl.load_workbook(path, read_only=True)['Label']
    hdr = None; out = []
    for r in ws.iter_rows(min_row=1, values_only=True):
        if hdr is None:
            if r and 'Row ID' in r and 'Your category' in r: hdr = (r.index('Row ID'), r.index('Your category'))
            continue
        if r[hdr[0]]: out.append(dict(row_id=str(r[hdr[0]]), human_slug=r[hdr[1]] or ''))
    return out

def spot(args):
    key = read_csv(os.path.join(args.out, 'gold.csv')); sheet = read_sheet(args.sheet)
    strata = C.defaultdict(list)
    for r in key:
        if r['status'] in ('gold', 'gold_flagged'):   # rows the labelers decided; rule/ruled rows are not model-built
            strata['none' if r['gold_slug'] == NONE else r['status']].append(r['row_id'])
    total = sum(len(v) for v in strata.values()); rng = random.Random(args.seed); pick = []
    for k in sorted(strata):
        n = min(len(strata[k]), max(3, round(args.n * len(strata[k]) / total)))
        pick += rng.sample(sorted(strata[k]), n)
    rng.shuffle(pick)
    out = [dict(sheet[i], human_slug='', unsure='', notes='') for i in pick]
    write_csv(os.path.join(args.out, 'spot_check.csv'), ['row_id', 'sku', 'name', 'description', 'human_slug', 'unsure', 'notes'], out)
    write_spot_xlsx(args.sheet, pick, os.path.join(args.out, 'spot_check.xlsx'), set(read_leaf(args.leaf)))
    print(f'{len(pick)} rows drawn (seed {args.seed}):', {k: sum(1 for i in pick if i in set(v)) for k, v in sorted(strata.items())})

def classify(key_slug, human_slug, leaf):
    """match | nonleaf (a person picked a parent/non-leaf category) | human_none | key_none | other"""
    if human_slug == key_slug: return 'match'
    if human_slug != NONE and human_slug not in leaf: return 'nonleaf'
    if human_slug == NONE: return 'human_none'
    if key_slug == NONE: return 'key_none'
    return 'other'

def load_answers(files):
    ans = {}
    for f in files:                       # later files override earlier ones (e.g. the redo sheet)
        for r in read_human(f):
            h = norm_slug(r.get('human_slug'))
            if h: ans[r['row_id']] = h
    return ans

def score(args):
    key = {r['row_id']: r for r in read_csv(os.path.join(args.out, 'gold.csv'))}
    leaf = set(read_leaf(args.leaf)); ans = load_answers(args.files)
    if not ans: print('no filled-in rows'); return
    kinds = C.defaultdict(list)
    skipped = [i for i in ans if key[i]['status'] == 'excluded']
    ans = {i: h for i, h in ans.items() if key[i]['status'] != 'excluded'}
    for i, h in ans.items(): kinds[classify(key[i]['gold_slug'], h, leaf)].append((i, key[i]['gold_slug'], h))
    n = len(ans); nl = len(kinds['nonleaf']); m = n - nl; k = len(kinds['match']); lo, hi = wilson(k, m)
    print(f'human labels: {n}' + (f' (+{len(skipped)} excluded rows not counted: {", ".join(skipped)})' if skipped else ''))
    if nl: print(f'  {nl} picked a non-leaf category (not scored; run "python gold.py redo <file>" to re-pick them)')
    print(f'  scored: {m}; match the key: {k} ({k/m:.1%}); 95% interval {lo:.1%} to {hi:.1%}')
    if nl: print(f'  if every non-leaf row were re-picked and matched: {(k+nl)/n:.1%}')
    for kind, label in (('human_none', 'person said none fits, key has a category'), ('key_none', 'key says none, person picked a category'),
                        ('other', 'different leaf category'), ('nonleaf', 'non-leaf pick (needs a leaf)')):
        if kinds[kind]:
            print(f'\n{label}: {len(kinds[kind])}')
            for i, g, h in kinds[kind]:
                print(f'  {i}: human={h}' if kind == 'nonleaf' else f'  {i}: key={g} human={h}')   # keep the key hidden until re-picked

def redo(args):
    leaf = set(read_leaf(args.leaf)); ans = load_answers([args.file])
    ids = [i for i, h in ans.items() if h != NONE and h not in leaf]
    if not ids: print('no non-leaf answers'); return
    out = os.path.join(args.out, 'spot_check_redo.xlsx')
    write_spot_xlsx(args.sheet, ids, out, leaf)          # row order = order in the filled-in file
    print(f'{len(ids)} rows to re-pick -> {out} (leaf categories only). Then: python gold.py score {args.file} {out}')

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('build', 'spot', 'score', 'redo'):
        s = sub.add_parser(name)
        s.add_argument('--out', default=P('gold')); s.add_argument('--sheet', default=P('gold', 'inputs', 'labeling_sheet.xlsx'))
        if name == 'build':
            s.add_argument('--a', default=P('gold', 'inputs', 'labels_A.csv')); s.add_argument('--b', default=P('gold', 'inputs', 'labels_B.csv'))
            s.add_argument('--leaf', default=P('reports', 'leaf_options.csv')); s.add_argument('--vendor', default=P('vendors', 'ashley.yaml'))
            s.add_argument('--rulings', default=P('gold', 'rulings.csv'))
        if name != 'build': s.add_argument('--leaf', default=P('reports', 'leaf_options.csv'))
        if name == 'spot': s.add_argument('--n', type=int, default=60); s.add_argument('--seed', type=int, default=7)
        if name == 'score': s.add_argument('files', nargs='+')
        if name == 'redo': s.add_argument('file')
    a = ap.parse_args(); {'build': build, 'spot': spot, 'score': score, 'redo': redo}[a.cmd](a)

if __name__ == '__main__': main()