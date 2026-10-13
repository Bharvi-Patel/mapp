# Cascade evaluation (trust_vendor_path=True, unreviewed_map=False, model step off)

Rows scored: 215 of 215 answer-key rows (0 had no raw item in the dump)

## Decided by rules (assigned)

| rule | decided | correct | precision |
|---|---|---|---|
| sku_prefix:100- | 53 | 53 | 100.0% |
| vendor_path_exact | 110 | 110 | 100.0% |
| **all rules** | 163 | 163 | 100.0% |

## Not decided: 52

| reason | rows | of which the key says "no category" |
|---|---|---|
| no_rule_no_model | 52 | 6 |

## Why the rules left them undecided

| why | itemType | rows | key says "no category" | key answer is among the options |
|---|---|---|---|---|
| component_or_excluded_only | Component | 20 | 0 | 12 of 20 |
| several_leaves | Item | 18 | 0 | 18 of 18 |
| path_has_no_leaf | Component | 6 | 5 | 0 of 1 |
| no_vendor_path | Item | 6 | 0 | 6 of 6 |
| no_vendor_path | Component | 1 | 0 | 1 of 1 |
| component_or_excluded_only | Item | 1 | 1 | 0 of 0 |

## Could a tie-break rule pick among several path leaves?

18 rows. Key is among the path leaves for 18. If the rule always took:
- the first leaf (deepest path first): 5 correct
- the last leaf: 12 correct

## Would go to the model

46 rows with a real answer. **The right category is among the options for 37 of them (80.4%)** (best the model step can do).
Options offered: {'<=3': 19, '4-8': 21, '9+': 6}
- missing: T0002 Paxberry Twin Panel Footboard with Rails | key=bedroom-furniture-beds | 5 options from class_pool
- missing: T0004 Lettner Bedroom Mirror | key=wall-decor-mirrors | 4 options from class_pool
- missing: T0005 Fynnegan Pillow | key=pillows-accent-pillows | 14 options from class_pool
- missing: T0040 Chalanna Bedroom Mirror | key=wall-decor-mirrors | 4 options from class_pool
- missing: T0076 Midnight-Madness Wedge | key=sofas-and-seating-sectional-sofas | 5 options from class_pool
- missing: T0080 Modmax Console with Storage | key=sofas-and-seating-sectional-sofas | 5 options from class_pool
- missing: T0179 Chalanna Queen/King Rails | key=bedroom-furniture-beds | 4 options from class_pool
- missing: T0194 Wynnlow King Panel Rails | key=bedroom-furniture-beds | 5 options from class_pool
- missing: T0212 Clarington Left-Arm Facing Sofa with Cor | key=sofas-and-seating-sectional-sofas | 5 options from class_pool
