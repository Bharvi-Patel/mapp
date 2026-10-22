import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from rollup_products import rollup

def run(decisions, code='Accent Cabinet', pieces=('r1',)):
    return rollup({'p': code}, {'p': list(pieces)}, decisions, {}, {})[0]

def test_navigable_categories_are_all_kept():
    r = run({'r1': ('assigned', 'dining-furniture-dining-storage', 'navigable_categories', ['dining-furniture-dining-storage', 'home-accents-accent-furniture'])})
    assert (r['state'], r['category'], r['rule']) == ('assigned', 'dining-furniture-dining-storage | home-accents-accent-furniture', 'navigable_categories')

def test_pieces_with_navigable_categories_are_unioned_not_tiebroken():
    r = run({'r1': ('assigned', 'a', 'navigable_categories', ['a', 'b']), 'r2': ('assigned', 'c', 'navigable_categories', ['c'])}, pieces=('r1', 'r2'))
    assert r['category'] == 'a | b | c' and r['state'] == 'assigned'

def test_old_single_decisions_unchanged():
    r = run({'r1': ('assigned', 'sofas', 'vendor_path_exact', None)})
    assert (r['state'], r['category'], r['rule']) == ('assigned', 'sofas', 'vendor_path_exact')

def run_cur(decisions, cur, code='Sectional', pieces=('r1', 'r2'), keep=False):
    return rollup({'p': code}, {'p': list(pieces)}, decisions, {}, {'p': set(cur)}, keep)[0]

def test_component_only_product_follows_its_navigable_component_category_by_default():
    r = run_cur({'r1': ('assigned', 'component-skus-living-room', 'component_sku', None), 'r2': ('assigned', 'component-skus-living-room', 'component_sku', None)}, {'living-room-sofas'})
    assert (r['state'], r['category'], r['rule']) == ('assigned', 'component-skus-living-room', 'component_sku')

def test_component_only_product_keeps_its_current_categories_when_opted_in():
    r = run_cur({'r1': ('assigned', 'component-skus-living-room', 'component_sku', None), 'r2': ('assigned', 'component-skus-living-room', 'component_sku', None)},
                {'living-room-sofas-and-seating-sectionals'}, keep=True)
    assert (r['state'], r['category'], r['rule'], r['vs_current']) == ('keep_current', 'living-room-sofas-and-seating-sectionals', 'keep_current:component_only', 'kept')

def test_component_only_pieces_in_different_rooms_keep_current_when_opted_in():
    r = run_cur({'r1': ('assigned', 'component-skus-living-room', 'component_sku', None), 'r2': ('assigned', 'component-skus-bedroom', 'component_sku', None)}, {'a', 'b'}, keep=True)
    assert (r['state'], r['category']) == ('keep_current', 'a | b')

def test_component_only_with_no_current_categories_falls_back_to_the_component_category():
    r = run_cur({'r1': ('assigned', 'component-skus-bedroom', 'component_sku', None)}, set(), pieces=('r1',), keep=True)
    assert (r['state'], r['category']) == ('assigned', 'component-skus-bedroom')

def test_a_real_piece_still_wins_over_component_pieces():
    r = run_cur({'r1': ('assigned', 'component-skus-bedroom', 'component_sku', None), 'r2': ('assigned', 'bedroom-furniture-beds', 'vendor_path_exact', None)}, {'x'})
    assert (r['state'], r['category']) == ('assigned', 'bedroom-furniture-beds')

def test_several_categories_from_the_keep_all_path_rule_survive_the_rollup():
    r = run({'r1': ('assigned', 'sofas-and-seating-reclining-loveseats', 'vendor_path_all_leaves', ['sofas-and-seating-reclining-loveseats', 'sofas-and-seating-power-reclining'])}, code='Loveseat')
    assert (r['state'], r['category'], r['rule']) == ('assigned', 'sofas-and-seating-power-reclining | sofas-and-seating-reclining-loveseats', 'vendor_path_all_leaves')