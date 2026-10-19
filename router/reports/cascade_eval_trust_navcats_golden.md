# Cascade evaluation (trust_vendor_path=True, unreviewed_map=False, model step off)

Rows scored: 4071 of 4326 answer-key rows (255 had no raw item in the dump)

## Decided by rules (assigned)

| rule | decided | correct | precision |
|---|---|---|---|
| item_class_map | 22 | 22 | 100.0% |
| name_rule | 197 | 193 | 98.0% |
| path_leaf_name_match | 399 | 399 | 100.0% |
| vendor_path_exact | 3256 | 3254 | 99.9% |
| **all rules** | 3874 | 3868 | 99.8% |

## Go-live check (target precision 99%, at least 30 gold rows)

| rule | rows | precision | 95% lower bound | verdict |
|---|---|---|---|---|
| item_class_map | 22 | 100.0% | 85.1% | shadow only: too few gold rows |
| name_rule | 197 | 98.0% | 94.9% | below target |
| path_leaf_name_match | 399 | 100.0% | 99.0% | ok to enable |
| vendor_path_exact | 3256 | 99.9% | 99.8% | ok to enable |

The lower bound is the plain-statistics floor on true precision given only these rows. A rule can pass the target here and still have a lower bound under it; the labeled rows are also the ones the rules were tuned on, so treat precision as optimistic.

## Not decided: 197

| reason | rows | of which the key says "no category" |
|---|---|---|
| no_rule_no_model | 197 | 0 |

## Why the rules left them undecided

| why | itemType | rows | key says "no category" | key answer is among the options |
|---|---|---|---|---|
| several_leaves | Item | 179 | 0 | 179 of 179 |
| no_vendor_path | Item | 18 | 0 | 18 of 18 |

## Could a tie-break rule pick among several path leaves?

179 rows. Key is among the path leaves for 179. If the rule always took:
- the first leaf (deepest path first): 176 correct
- the last leaf: 3 correct

## Would go to the model

197 rows with a real answer. **The right category is among the options for 197 of them (100.0%)** (best the model step can do).
Options offered: {'<=3': 179, '4-8': 17, '9+': 1}
