"""Print what the router saw for the two golden disagreements. Run from the router folder: python show_two.py"""
import csv
from dumpreader import rows
want = {'A3000325', 'B822-01'}
nav = {}
with open('navcats_merged.csv', newline='', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        if r['sku'] in want: nav[r['sku']] = r['navigableCategories']
for r in rows('dump_for_evidence.sql', 'pim_raw_items'):
    if r['sku'] in want:
        print(r['sku'], '|', r['itemName'], '|', r['itemType'], '|', r['itemClass'])
        print('   Ashley path:', nav.get(r['sku']))