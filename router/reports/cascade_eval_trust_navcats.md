# Cascade evaluation (trust_vendor_path=True, unreviewed_map=False, model step off)

Rows scored: 215 of 215 answer-key rows (0 had no raw item in the dump)

## Decided by rules (assigned)

| rule | decided | correct | precision |
|---|---|---|---|
| item_class_map | 1 | 0 | 0.0% |
| name_rule | 13 | 13 | 100.0% |
| path_leaf_name_match | 8 | 7 | 87.5% |
| sku_prefix:100- | 53 | 53 | 100.0% |
| vendor_path_exact | 107 | 107 | 100.0% |
| **all rules** | 182 | 180 | 98.9% |

## Go-live check (target precision 99%, at least 30 gold rows)

| rule | rows | precision | 95% lower bound | verdict |
|---|---|---|---|---|
| item_class_map | 1 | 0.0% | 0.0% | shadow only: too few gold rows |
| name_rule | 13 | 100.0% | 77.2% | shadow only: too few gold rows |
| path_leaf_name_match | 8 | 87.5% | 52.9% | shadow only: too few gold rows |
| sku_prefix:100- | 53 | 100.0% | 93.2% | ok to enable |
| vendor_path_exact | 107 | 100.0% | 96.5% | ok to enable |

The lower bound is the plain-statistics floor on true precision given only these rows. A rule can pass the target here and still have a lower bound under it; the labeled rows are also the ones the rules were tuned on, so treat precision as optimistic.

## Components (decision A: follow Ashley's component-skus-* category)

21 Component rows assigned by rule component_sku. Not scored against the key: the key labels them with real categories, by design.
The key says "no category" for 1 of them (check those).
- component-skus-bedroom: 13
- component-skus-living-room: 7
- component-skus-outdoor: 1

## Not decided: 12

| reason | rows | of which the key says "no category" |
|---|---|---|
| no_rule_no_model | 12 | 5 |

## Why the rules left them undecided

| why | itemType | rows | key says "no category" | key answer is among the options |
|---|---|---|---|---|
| path_has_no_leaf | Component | 6 | 5 | 0 of 1 |
| no_vendor_path | Item | 3 | 0 | 3 of 3 |
| several_leaves | Item | 2 | 0 | 2 of 2 |
| no_vendor_path | Component | 1 | 0 | 1 of 1 |

## Could a tie-break rule pick among several path leaves?

2 rows. Key is among the path leaves for 2. If the rule always took:
- the first leaf (deepest path first): 1 correct
- the last leaf: 1 correct

## Would go to the model

7 rows with a real answer. **The right category is among the options for 6 of them (85.7%)** (best the model step can do).
Options offered: {'9+': 2, '4-8': 3, '<=3': 2}
- missing: T0005 Fynnegan Pillow | key=pillows-accent-pillows | 14 options from class_pool
