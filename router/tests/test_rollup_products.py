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
