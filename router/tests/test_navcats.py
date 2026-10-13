import os, sys, csv, json
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, '..'))
import cascade as X
import fetch_navcats as F

NAV = ['Bedroom', 'Bedroom - Bedroom Furniture', 'Bedroom - Bedroom Furniture - Beds']

def test_find_product_in_single_object_list_and_wrapper():
    p = {'sku': 'B730B11', 'navigableCategories': NAV}
    assert F.find_product(p, 'B730B11') is p
    assert F.find_product([{'sku': 'X', 'navigableCategories': []}, p], 'b730b11') is p
    assert F.find_product({'data': {'items': [p]}}, 'B730B11') is p
    assert F.find_product({'sku': 'B730B11'}, 'B730B11') is None          # no field -> no_field row

def test_load_navcats_roundtrip(tmp_path):
    f = tmp_path / 'n.csv'
    with open(f, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['sku', 'navigableCategories', 'status'])
        w.writerow(['B730B11', json.dumps(NAV), 'ok']); w.writerow(['A60002521', json.dumps(['Uncategorized']), 'ok'])
        w.writerow(['MISSING', '', 'not_found'])
    got = X.load_navcats(str(f))
    assert got['B730B11'][0] == 'BEDROOMBEDROOMFURNITUREBEDS'
    assert got['A60002521'] == [] and got['MISSING'] == []