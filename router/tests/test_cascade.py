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