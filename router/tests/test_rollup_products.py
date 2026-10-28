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

def test_check_package_statuses():
    from check_package import compare
    rules = {'Bedroom Package': 'bedroom-sets'}
    products = {'a': 'Bedroom Package', 'b': 'Bedroom Package', 'c': 'Bedroom Package', 'd': 'Bed'}
    raw_of = {'a': ['a1'], 'b': ['b1'], 'c': ['c1'], 'd': ['d1']}
    dec = {'a1': ('assigned', 'bedroom-sets', 'navigable_categories', ['bedroom-sets', 'kids-furniture-beds']),
           'b1': ('assigned', 'kids-furniture-beds', 'navigable_categories', None),
           'c1': ('assigned', 'component-skus-bedroom', 'component_sku', None), 'd1': ('assigned', 'x', 'r', None)}
    got = {r['product']: r['status'] for r in compare(products, raw_of, dec, rules, {})}
    assert got == {'a': 'agree', 'b': 'differ', 'c': 'only_components'}      # 'd' is not a package code

def run_kit(kit_nav, cur, code='Bed', pieces=('r1',), decisions=None):
    decisions = decisions or {'r1': ('assigned', 'component-skus-bedroom', 'component_sku', None)}
    return rollup({'p': code}, {'p': list(pieces)}, decisions, {}, {'p': set(cur)}, False, kit_nav)[0]

def test_kit_takes_its_own_categories_not_the_component_pick():
    r = run_kit({'p': ['bedroom-furniture-beds']}, {'bedroom-furniture-beds'})
    assert (r['state'], r['category'], r['rule'], r['vs_current']) == ('assigned', 'bedroom-furniture-beds', 'kit_navigable_categories', 'already_linked')

def test_kit_with_several_categories_is_compared_as_a_set():
    assert run_kit({'p': ['a', 'b']}, {'a', 'b', 'c'})['vs_current'] == 'already_linked'
    assert run_kit({'p': ['a', 'b']}, {'a'})['vs_current'] == 'would_add'

def test_kit_with_no_usable_leaf_goes_to_review_and_adds_nothing():
    r = run_kit({'p': []}, {'bedroom'})
    assert (r['state'], r['rule'], r['vs_current']) == ('review', 'kit_no_usable_leaf', '')

def test_kit_without_fetched_categories_keeps_the_old_logic():
    r = run_kit({}, {'bedroom-furniture-beds'})
    assert (r['state'], r['category'], r['rule']) == ('assigned', 'component-skus-bedroom', 'component_sku')
def test_multi_category_navigable_rows_are_compared_as_a_set_not_left_blank():
    import rollup_products as R
    dec = {'r1': ('assigned', 'a', 'navigable_categories', ['a', 'b'])}
    def run(cur): return R.rollup({'p': 'Bed'}, {'p': ['r1']}, dec, {}, {'p': cur})[0]['vs_current']
    assert run({'a', 'b', 'c'}) == 'already_linked'
    assert run({'a'}) == 'would_add'
    assert run(set()) == 'no_links'

def test_kit_filed_only_under_component_leaves_gets_its_own_rule_and_is_compared_to_current():
    r = run_kit({'p': ['component-skus-bedroom']}, {'bedroom'})
    assert (r['state'], r['category'], r['rule'], r['vs_current']) == ('assigned', 'component-skus-bedroom', 'kit_component_categories', 'would_add')
    assert run_kit({'p': ['component-skus-bedroom']}, {'component-skus-bedroom'})['vs_current'] == 'already_linked'

def test_kit_with_a_real_leaf_keeps_the_normal_rule_name():
    assert run_kit({'p': ['bedroom-furniture-beds']}, {'bedroom'})['rule'] == 'kit_navigable_categories'

def test_kit_slugs_falls_back_to_component_leaves_only_when_nothing_else_is_usable():
    import rollup_products as R
    from types import SimpleNamespace as NS
    res = NS(cfg={'component_rule': {'slug_prefix': 'component-skus-'}}, vendor_map={}, code_slug={'C1': 'component-skus-bedroom', 'B1': 'bedroom-furniture-beds', 'U1': 'uncategorized'},
             leaf={'component-skus-bedroom', 'bedroom-furniture-beds', 'uncategorized'}, store={'component-skus-bedroom', 'bedroom-furniture-beds', 'uncategorized'},
             excluded={'component-skus-bedroom', 'uncategorized'}, inactive=set())
    assert R.kit_slugs(['C1'], res) == ['component-skus-bedroom']
    assert R.kit_slugs(['C1', 'B1'], res) == ['bedroom-furniture-beds']
    assert R.kit_slugs(['U1'], res) == []

def test_batch3_picks_only_the_approved_groups_and_never_a_link_that_exists():
    import apply_batch3 as B
    def row(p, code, cat, rule, cur, state='assigned'): return dict(product=p, item_code=code, category=cat, rule=rule, current=cur, state=state)
    rows = [row('p1', 'Dresser', 'bedroom-furniture-dressers-and-chests | wall-decor-mirrors', 'navigable_categories', 'bedroom'),     # A + C
            row('p2', 'Barstool', 'bar-furniture-bar-stools | bar-furniture-counter-chairs', 'navigable_categories', 'bar-furniture-bar-stools'),   # bar stools already linked, counter chairs is C
            row('p3', 'Bed', 'component-skus-bedroom', 'kit_component_categories', 'bedroom'),                                          # D
            row('p4', 'Bed', 'kids-furniture-headboards', 'navigable_categories', 'bedroom'),                                           # held back
            row('p5', 'Dresser', 'bedroom-furniture-dressers-and-chests', 'navigable_categories', 'bedroom'),                           # in the approved batch already
            row('p6', 'Dresser', 'bedroom-furniture-dressers-and-chests', 'navigable_categories', 'bedroom', state='review'),
            row('p7', 'Bedroom Package', 'bedroom-sets', 'package:Bedroom Package', 'bedroom'),                                         # package rule, not Ashley's navigable categories
            row('p8', 'Sectional', 'home-accents-accent-chairs', 'navigable_categories', 'living-room'),                                 # on the dropped list
            row('p9', 'Bed', 'component-skus-bedroom', 'navigable_categories', 'bedroom')]                                              # component slug, not a kit
    got = B.pick_links(rows, already={('p5', 'bedroom-furniture-dressers-and-chests')}, dropped_products={'p8'})
    assert got == [('p1', 'bedroom-furniture-dressers-and-chests', 'Dresser', 'bedroom', 'A'), ('p1', 'wall-decor-mirrors', 'Dresser', 'bedroom', 'C'),
                   ('p2', 'bar-furniture-counter-chairs', 'Barstool', 'bar-furniture-bar-stools', 'C'), ('p3', 'component-skus-bedroom', 'Bed', 'bedroom', 'D')]