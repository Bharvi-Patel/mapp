import os, sys
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, '..'))
import cascade as X
from cascade import Resources, MemoryStore, route, NONE_OF_THESE
from contract import RouterInput

def cfg(**kw):
    c = {'vendor_id': 'v', 'version': '1', 'field_map': {}, 'settings': {'trust_vendor_path': False, 'thresholds': None},
         'sku_prefix_rules': {'100-': 'store-displays'}, 'package_rules': {'Bedroom Package': 'bedroom-sets'},
         'review_classes': ['REPL'], 'contradictions': []}
    c.update(kw); return c

LEAF = {'sofas', 'ottomans', 'rugs-area-rugs', 'bedroom-sets', 'nursery-cribs'}
def res(**kw):
    c = kw.pop('cfg', cfg())
    r = Resources(c, LEAF, LEAF - {'nursery-cribs'} | {'store-displays'}, {'store-displays'}, {'store-displays'},
                  {'CLS': ['sofas', 'ottomans'], 'ONE': ['rugs-area-rugs']}, {'MAPCODE': 'sofas'}, MemoryStore())
    for k, v in kw.items(): setattr(r, k, v)
    return r
def inp(**kw):
    d = dict(vendor_id='v', subject_type='raw_item', subject_uuid='u1', sku='S1', name='Thing', item_class='CLS', vendor_category_path=[])
    d.update(kw); return RouterInput(**d)
class Model:
    def __init__(self, choice, probs): self.a = {'choice': choice, 'probabilities': probs}
    def classify(self, i, options): return self.a

def test_sku_prefix_goes_to_excluded_store_displays_even_though_excluded():
    o = route(inp(sku='100-7'), res())
    assert (o.outcome, o.primary_slug, o.rule) == ('assigned', 'store-displays', 'sku_prefix:100-')

def test_package_rule_only_for_products():
    assert route(inp(subject_type='product', item_code='Bedroom Package'), res()).primary_slug == 'bedroom-sets'
    assert route(inp(item_code='Bedroom Package'), res()).outcome == 'review'

def test_review_class_goes_to_review():
    o = route(inp(item_class='REPL'), res()); assert (o.outcome, o.review_reason) == ('review', 'review_class')

def test_reuse_and_human_come_first_and_are_validated():
    r = res(); i = inp(sku='S9'); h = X.K.content_hash(i)
    r.decisions.reuse[('v', 'S9', h)] = ('ottomans', 0.9)
    assert route(i, r).stage == 'reuse'
    r2 = res(); r2.decisions.human[('v', 'raw_item', 'u1')] = 'nursery-cribs'      # category not in the store
    o = route(inp(), r2); assert (o.outcome, o.review_reason) == ('review', 'not_in_store')

def test_vendor_path_only_when_trusted():
    i = inp(vendor_category_path=['rugs-area-rugs'])
    assert route(i, res(), None, False).outcome == 'review'
    assert route(i, res(), None, True).rule == 'vendor_path_exact'

def test_vendor_path_contradiction():
    c = cfg(contradictions=[{'slug_prefix': 'rugs-', 'name_pattern': 'pillow'}])
    o = route(inp(name='Throw Pillow', vendor_category_path=['rugs-area-rugs']), res(cfg=c), None, True)
    assert (o.outcome, o.review_reason) == ('review', 'contradiction')

def test_two_path_leaves_narrow_the_options_then_review_without_model():
    o = route(inp(vendor_category_path=['sofas', 'ottomans', 'rugs-area-rugs'], item_class='NOPOOL'), res(), None, True)
    assert o.review_reason == 'no_rule_no_model' and [c['slug'] for c in o.candidates] == ['sofas', 'ottomans', 'rugs-area-rugs']

def test_no_pool_is_review():
    assert route(inp(item_class='UNKNOWN'), res()).review_reason == 'no_pool'

def test_model_outcomes():
    t = cfg(); t['settings']['thresholds'] = {'999': 0.85}
    good = Model('ottomans', {'ottomans': 0.99, 'sofas': 0.01})
    o = route(inp(), res(cfg=t), good); assert (o.outcome, o.stage, o.confidence) == ('assigned', 'model', 0.95)   # capped
    assert route(inp(), res(cfg=cfg()), good).review_reason == 'below_threshold'                                  # no threshold: fail closed
    assert route(inp(), res(cfg=t), Model('ottomans', {'ottomans': 0.6, 'sofas': 0.4})).review_reason == 'below_threshold'
    assert route(inp(), res(cfg=t), Model(NONE_OF_THESE, {})).review_reason == 'none_of_these'
    assert route(inp(), res(cfg=t), Model('rugs-area-rugs', {'rugs-area-rugs': 0.99})).review_reason == 'not_offered'

def test_threshold_lookup():
    c = cfg(); c['settings']['thresholds'] = {'3': 0.8, '8': 0.85, '999': 0.9}
    assert [X.threshold_for(c, n) for n in (2, 5, 20)] == [0.8, 0.85, 0.9]
# ---- real Ashley navigableCategories -> codes
def test_nav_code_matches_stored_code_shape():
    assert X.nav_code('Bedroom - Bedroom Furniture - Beds') == 'BEDROOMBEDROOMFURNITUREBEDS'
    assert X.nav_code('Rugs and Decor - Rugs - Indoor/Outdoor Rugs') == 'RUGSANDDECORRUGSINDOOR/OUTDOORRUGS'   # slash kept
    assert X.nav_code('Living Room - Tables - 3-Pack Tables') == 'LIVINGROOMTABLES3PACKTABLES'                  # inner hyphen dropped

def test_nav_codes_deepest_first_dedupes_and_drops_uncategorized():
    nav = ['Bedroom', 'Bedroom - Bedroom Furniture', 'Bedroom - Bedroom Furniture - Beds']
    assert X.nav_codes(nav) == ['BEDROOMBEDROOMFURNITUREBEDS', 'BEDROOMBEDROOMFURNITURE', 'BEDROOM']
    assert X.nav_codes(['Uncategorized']) == []
    assert X.nav_codes('["Bedroom"]') == ['BEDROOM']          # JSON text from a CSV cell
    assert X.nav_codes(None) == []

def test_real_codes_hit_vendor_map_then_leaf_lookup():
    r = res(); r.cfg['settings']['trust_vendor_path'] = True
    r.vendor_map = {'BEDROOMBEDROOMFURNITUREBEDS': 'sofas'}
    assert route(inp(vendor_category_path=X.nav_codes(['Bedroom - Bedroom Furniture - Beds'])), r).rule == 'vendor_map'
    r2 = res(); r2.cfg['settings']['trust_vendor_path'] = True
    r2.code_slug = {'RUGSANDDECORRUGSAREARUGS': 'rugs-area-rugs'}      # not in the accepted map: step 6 resolves it by code
    o = route(inp(vendor_category_path=['RUGSANDDECORRUGSAREARUGS']), r2)
    assert (o.outcome, o.primary_slug, o.rule) == ('assigned', 'rugs-area-rugs', 'vendor_path_exact')

# ---- children of an excluded parent are excluded too
def test_excluded_target_in_vendor_map_is_skipped_not_assigned():
    r = res(); r.cfg['settings']['trust_vendor_path'] = True
    r.excluded = r.excluded | {'comp-bedroom'}
    r.vendor_map = {'COMPBEDROOM': 'comp-bedroom', 'OKCODE': 'sofas'}
    o = route(inp(vendor_category_path=['COMPBEDROOM', 'OKCODE']), r)       # first code is excluded -> next one is used
    assert (o.outcome, o.primary_slug, o.rule) == ('assigned', 'sofas', 'vendor_map')

def test_excluded_only_vendor_leaf_falls_through_to_class_pool():
    r = res(); r.cfg['settings']['trust_vendor_path'] = True
    r.excluded = r.excluded | {'comp-bedroom'}; r.leaf = r.leaf | {'comp-bedroom'}; r.store = r.store | {'comp-bedroom'}
    r.code_slug = {'COMPBEDROOM': 'comp-bedroom'}
    o = route(inp(vendor_category_path=['COMPBEDROOM']), r)
    assert o.outcome == 'review' and o.review_reason == 'no_rule_no_model'   # no wrong assignment; the pool offers sofas, ottomans

def test_undecided_why_classifies_the_vendor_path():
    r = res(); r.excluded = r.excluded | {'comp'}; r.leaf = r.leaf | {'comp'}; r.store = r.store | {'comp'}
    r.code_slug = {'C1': 'comp', 'S1': 'sofas', 'O1': 'ottomans', 'N1': 'nursery-cribs'}
    why = lambda path: X.undecided_why(inp(vendor_category_path=path), r)
    assert why([]) == 'no_vendor_path'
    assert why(['PARENTONLY']) == 'path_has_no_leaf'
    assert why(['C1']) == 'component_or_excluded_only'
    assert why(['S1', 'O1']) == 'several_leaves'
    assert why(['N1']) == 'leaf_not_in_store'
    assert why(['S1']) == 'one_leaf_but_not_assigned'

def test_usable_leaves_keeps_path_order_and_drops_excluded_and_unknown():
    r = res(); r.excluded = r.excluded | {'comp'}; r.leaf = r.leaf | {'comp'}; r.store = r.store | {'comp'}
    r.code_slug = {'C1': 'comp', 'S1': 'sofas', 'O1': 'ottomans'}
    assert X.usable_leaves(inp(vendor_category_path=['O1', 'C1', 'PARENT', 'S1', 'O1']), r) == ['ottomans', 'sofas']

def test_pick_by_name_patterns():
    from cascade import pick_by_name
    assert pick_by_name('Anniversary Edition Plush Twin Mattress',
                        ['mattresses-and-bases-by-type-innerspring', 'mattresses-by-size-twin']) == 'mattresses-by-size-twin'
    assert pick_by_name('Hessland 8 x 10 Washable Rug', ['rugs-area-rugs', 'rugs-washable']) == 'rugs-washable'
    assert pick_by_name('Dushland Indoor/Outdoor Large Rug',
                        ['patio-accessories-indoor-outdoor-rugs', 'rugs-indoor-outdoor-rugs', 'rugs-area-rugs']) == 'rugs-indoor-outdoor-rugs'
    assert pick_by_name('Plain Thing', ['a-one', 'b-two']) is None      # no clear winner stays undecided
    assert pick_by_name('x', ['only-one']) is None


def test_component_rule_assigns_the_parts_category_only_for_components():
    c = cfg(component_rule={'item_type': 'Component', 'slug_prefix': 'component-skus-'})
    leaf = LEAF | {'component-skus-bedroom'}
    r = Resources(c, leaf, leaf - {'nursery-cribs'} | {'store-displays'}, {'store-displays'}, {'store-displays', 'component-skus-bedroom'},
                  {}, {}, MemoryStore())
    p = ['component-skus-bedroom', 'component-skus']
    o = route(inp(item_type='Component', vendor_category_path=p), r, None, True)
    assert (o.outcome, o.primary_slug, o.rule) == ('assigned', 'component-skus-bedroom', 'component_sku')
    assert route(inp(item_type='Item', vendor_category_path=p), r, None, True).outcome == 'review'      # not a Component
    assert route(inp(item_type='Component', vendor_category_path=p), r, None, False).outcome == 'review'   # vendor path not trusted
    assert route(inp(item_type='Component', vendor_category_path=['component-skus']), r, None, True).outcome == 'review'   # parent only
def test_item_class_map_assigns_without_a_path_even_with_trust_off():
    o = route(inp(), res(item_class_map={'CLS': 'ottomans'}))
    assert (o.outcome, o.primary_slug, o.rule) == ('assigned', 'ottomans', 'item_class_map')

def test_item_class_map_skips_excluded_or_missing_targets():
    assert route(inp(), res(item_class_map={'CLS': 'store-displays'})).rule != 'item_class_map'   # excluded
    assert route(inp(), res(item_class_map={'CLS': 'nursery-cribs'})).rule != 'item_class_map'    # leaf, but not in the store

NAME_RULES = [{'pattern': r'\b(?P<size>split california king|split king|california king|twin xl|twin|full|queen|king)\s+mattress\s*$',
               'template': 'mattresses-by-size-{size}'}]
def res_mattress(**kw):
    r = res(cfg=cfg(name_rules=NAME_RULES))
    r.leaf = r.leaf | {'mattresses-by-size-twin-xl', 'mattresses-by-size-california-king', 'mattresses-by-size-king'}
    r.store = r.store | {'mattresses-by-size-twin-xl', 'mattresses-by-size-california-king', 'mattresses-by-size-king'}
    return r

def test_name_rule_sends_a_sized_mattress_to_its_size_category():
    for name, slug in [('Dreamcloud Premier Memory Foam Twin XL Mattress', 'mattresses-by-size-twin-xl'),
                       ('Firm Luxe 2.0 California King Mattress', 'mattresses-by-size-california-king'),
                       ('Dreamcloud Classic Memory Foam King Mattress', 'mattresses-by-size-king')]:
        o = route(inp(name=name), res_mattress())
        assert (o.outcome, o.primary_slug, o.rule) == ('assigned', slug, 'name_rule')

def test_name_rule_ignores_protectors_displays_and_unlisted_sizes():
    for name in ['Serenity Sleep Twin Mattress Protector', 'Queen Mattress Topper', 'Cooling Full XL Mattress']:
        assert route(inp(name=name), res_mattress()).rule != 'name_rule'

def test_name_rule_needs_the_size_category_to_exist_in_the_store():
    assert route(inp(name='Plush Queen Mattress'), res_mattress()).rule != 'name_rule'    # queen slug is not in the test store

class Boom:
    def classify(self, i, options): raise AssertionError('the model must not be called')

def test_no_text_skips_the_model():
    o = route(inp(name='  ', description=None), res(), Boom())
    assert (o.outcome, o.review_reason) == ('review', 'no_text')

def test_make_model_is_off_unless_asked():
    import types
    assert X.make_model(types.SimpleNamespace(use_model=False), cfg()) is None

import model_step as MS
class FakeJev(MS.JevModel):
    def __init__(self, answer, **kw): super().__init__(api_key='k', **kw); self.answer = answer; self.sent = []
    def _post(self, body): self.sent.append(body); return {'answers': {'category': self.answer}}
def jev_res(**settings):
    s = {'trust_vendor_path': False, 'thresholds': {'999': 0.8}}; s.update(settings)
    return res(cfg=cfg(settings=s))

def test_jev_request_describes_every_option_and_offers_none():
    m = FakeJev({'choice': 'sofas', 'probabilities': {'sofas': 0.9, 'ottomans': 0.1, 'none_of_these': 0}}, labels={'sofas': 'Sofas'})
    m.classify(inp(name='Camden Sofa'), ['sofas', 'ottomans'])
    body = m.sent[0]; q = body['questions']['category']
    assert q['type'] == 'choice' and set(q['criteria']) == {'sofas', 'ottomans', 'none_of_these'}
    assert q['criteria']['sofas'] == 'Sofas' and body['state']['name'] == 'Camden Sofa'

def test_jev_confident_clear_pick_is_assigned():
    m = FakeJev({'choice': 'sofas', 'probabilities': {'sofas': 0.9, 'ottomans': 0.1, 'none_of_these': 0}})
    o = route(inp(), jev_res(min_margin=0.3), m)
    assert (o.outcome, o.primary_slug, o.stage) == ('assigned', 'sofas', 'model')

def test_jev_near_tie_goes_to_review_even_above_threshold():
    m = FakeJev({'choice': 'sofas', 'probabilities': {'sofas': 0.55, 'ottomans': 0.45, 'none_of_these': 0}})
    o = route(inp(), jev_res(thresholds={'999': 0.5}, min_margin=0.3), m)
    assert (o.outcome, o.review_reason) == ('review', 'too_close')

def test_jev_none_of_these_and_low_confidence_go_to_review():
    m = FakeJev({'choice': 'none_of_these', 'probabilities': {'sofas': 0.1, 'ottomans': 0.1, 'none_of_these': 0.8}})
    assert route(inp(), jev_res(), m).review_reason == 'none_of_these'
    m = FakeJev({'choice': 'sofas', 'probabilities': {'sofas': 0.6, 'ottomans': 0.3, 'none_of_these': 0.1}})
    assert route(inp(), jev_res(), m).review_reason == 'below_threshold'

def test_jev_failure_sends_the_product_to_review():
    class Down(FakeJev):
        def _post(self, body): raise RuntimeError('boom')
    m = Down({}); o = route(inp(), jev_res(), m)
    assert o.outcome == 'review' and m.errors and 'boom' in m.first_error

def test_make_model_jev_needs_a_key(monkeypatch):
    import types
    for k in ('OPENROUTER_API_KEY', 'TYPESAFE_API_KEY'): monkeypatch.delenv(k, raising=False)
    a = types.SimpleNamespace(use_model=True, provider='jev', model_name=None, base_url=None, max_model_calls=5, pause_seconds=0.0)
    try: X.make_model(a, cfg()); assert False, 'should need a key'
    except SystemExit: pass
    monkeypatch.setenv('OPENROUTER_API_KEY', 'k')
    assert isinstance(X.make_model(a, cfg()), MS.JevModel)

def test_eval_and_shadow_share_make_model_for_jev(monkeypatch):
    import argparse, model_step as MS
    base = dict(use_model=True, provider='jev', model_name=None, base_url=None, max_model_calls=None, pause_seconds=0.0)
    cfg = {'settings': {}, 'tie_prefer': None}
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False); monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    try: X.make_model(argparse.Namespace(**base), cfg); assert False, 'should need a key'
    except SystemExit: pass
    monkeypatch.setenv('OPENROUTER_API_KEY', 'k')
    m = X.make_model(argparse.Namespace(**base), cfg)
    assert isinstance(m, MS.JevModel)
    assert X.make_model(argparse.Namespace(**{**base, 'use_model': False}), cfg) is None


def test_golden_key_and_loader(tmp_path):
    f = tmp_path / 'g.jsonl'
    f.write_text('{"sku":"1","accept":["a","b"]}\n{"sku":"2","accept":[]}\n{"sku":"3","accept":["c"]}\n', encoding='utf-8')
    rows = X.load_golden(str(f))
    assert [r['sku'] for r in rows] == ['1', '3'] and rows[0]['accept'] == ['a', 'b'] and rows[0]['gold_slug'] == 'a'
    assert X.golden_key(['a', 'b'], {'b'}, ['a']) == 'b'          # the router picked an accepted slug: that is the key, so it counts as correct
    assert X.golden_key(['a', 'b'], {'z'}, ['x', 'b']) == 'b'     # wrong pick: key is the accepted slug that was among the options
    assert X.golden_key(['a', 'b'], set(), ['x']) == 'a'          # nothing offered: first accepted


def _golden_res(**kw):
    cfg = {'version': '1', 'settings': {}}
    return Resources(cfg, {'a', 'b', 'bad'}, {'a', 'b'}, set(), {'bad'}, {}, {}, MemoryStore(), {}, {}, {}, **kw)


def test_golden_map_step():
    inp = RouterInput('ashley', 'raw_item', 'u1', 'S1', 'Thing')
    assert route(inp, _golden_res()).outcome == 'review'                                    # step off when no golden given
    out = route(inp, _golden_res(golden={'S1': ['bad', 'b']}))                              # 'bad' is excluded, so the next accepted slug is used
    assert (out.outcome, out.primary_slug, out.stage, out.rule) == ('assigned', 'b', 'rule', 'golden_map')
    out = route(inp, _golden_res(golden={'S1': ['bad']}))                                   # nothing the store can take -> review, never a bad assignment
    assert out.outcome == 'review'
    other = RouterInput('ashley', 'raw_item', 'u2', 'S2', 'Other')
    assert route(other, _golden_res(golden={'S1': ['a']})).outcome == 'review'              # SKUs not in golden fall through