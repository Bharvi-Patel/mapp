import json, os, sys
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, '..', 'contract'))
import jsonschema, sqlglot
from contract import *

ROOT = os.path.join(HERE, '..')
def schema(n): return json.load(open(os.path.join(ROOT, 'contract', n)))

def inp(**kw):
    d = dict(vendor_id='ashley', subject_type='raw_item', subject_uuid='u1', sku='B181-31', name='Dresser')
    d.update(kw); return RouterInput(**d)

def test_hash_stable_and_content_only():
    a = inp(); b = inp(subject_uuid='other', sku='X', name='  dresser ')
    assert content_hash(a) == content_hash(b)          # id fields and case/space ignored
    assert content_hash(a) != content_hash(inp(item_class='CASEGOOD'))
    assert content_hash(a) != content_hash(inp(vendor_category_path=['Bedroom']))

def test_input_schema():
    jsonschema.validate(to_dict(inp()), schema('input.schema.json'))

def mk(**kw):
    d = dict(outcome='assigned', primary_slug='bedroom-sets', stage='rule', rule='package_item_code',
             confidence=None, version='0.1', content_hash=content_hash(inp()))
    d.update(kw); return RouterOutput(**d)

def test_output_schema_assigned_and_review():
    s = schema('output.schema.json')
    jsonschema.validate(to_dict(mk()), s)
    jsonschema.validate(to_dict(mk(outcome='review', primary_slug=None, stage='review', rule='none', review_reason='none_of_these')), s)
    for bad in (mk(primary_slug=None), mk(outcome='review', review_reason='x')):
        try: jsonschema.validate(to_dict(bad), s); assert False
        except jsonschema.ValidationError: pass

KW = dict(allowed_slugs={'bedroom-sets', 'bedroom'}, leaf_slugs={'bedroom-sets'},
          excluded_slugs={'uncategorized'}, store_slugs={'bedroom-sets'})
def test_validator():
    assert validate_output(mk(), **KW) == []
    assert 'not_leaf' in validate_output(mk(primary_slug='bedroom'), **KW)       # parent rejected
    assert 'not_offered' in validate_output(mk(primary_slug='nursery-cribs'), **KW)
    kw = dict(KW, allowed_slugs=KW['allowed_slugs'] | {'nursery-cribs'}, leaf_slugs=KW['leaf_slugs'] | {'nursery-cribs'})
    assert 'not_in_store' in validate_output(mk(primary_slug='nursery-cribs'), **kw)  # unsynced category

def test_threshold_fails_closed():
    assert not model_decision_ok(0.99, None)
    assert model_decision_ok(0.9, 0.85) and not model_decision_ok(0.8, 0.85)

def test_configs_load():
    for f in ('ashley.yaml', '_template.yaml'):
        load_vendor_config(os.path.join(ROOT, 'vendors', f))
    assert load_vendor_config(os.path.join(ROOT, 'vendors', 'ashley.yaml'))['settings']['trust_vendor_path'] is False

def test_sql_parses():
    stmts = sqlglot.parse(open(os.path.join(ROOT, 'contract', 'schema.sql')).read(), read='mysql')
    from sqlglot import exp
    assert len([s for s in stmts if isinstance(s, exp.Create)]) == 2
