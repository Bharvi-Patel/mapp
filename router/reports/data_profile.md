# Data profile

## 1. Categories
| measure | pim_categories (master) | categories (store) |
|---|---|---|
| rows | 197 | 193 |
| active/enabled | 196 | 192 |
| top-level (parent_id 0) | 11 | 11 |
| has children (parents) | 34 | - |
| leaf (no children) | 162 | - |
| slug unique | True | True |

Master-only (not synced to store): **4** -> home-accents-accent-chairs, nursery-cribs, kids-bedding-mattress-pads-and-covers, kids-bedding-sheets
Store-only: **0** -> 

Excluded slugs present in master: component-skus (id 169, parent 0), uncategorized (id 180, parent 0)

Duplicate category names among enabled master categories: **20**
- "bar furniture": outdoor-dining-bar-furniture (parent Outdoor Dining), dining-room-bar-furniture (parent Dining Room)
- "bar stools": bar-furniture-bar-stools (parent Bar Furniture), outdoor-dining-bar-stools (parent Outdoor Dining)
- "bedroom": bedroom (parent -), component-skus-bedroom (parent Component SKUs)
- "beds": kids-furniture-beds (parent Kids Furniture), bedroom-furniture-beds (parent Bedroom Furniture), nursery-beds (parent Nursery), pets-beds (parent Pets)
- "desks": kids-furniture-desks (parent Kids Furniture), home-office-and-study-desks (parent Home Office and Study)
- "dining accessories": home-accents-dining-accessories (parent Home Accents), rugs-and-decor-dining-accessories (parent Rugs and Decor)
- "dressers and chests": kids-furniture-dressers-and-chests (parent Kids Furniture), bedroom-furniture-dressers-and-chests (parent Bedroom Furniture)
- "headboards": kids-furniture-headboards (parent Kids Furniture), bedroom-furniture-headboards (parent Bedroom Furniture)
- "home office": home-office (parent -), component-skus-home-office (parent Component SKUs)
- "indoor/outdoor rugs": patio-accessories-indoor-outdoor-rugs (parent Patio Accessories), rugs-indoor-outdoor-rugs (parent Rugs)
- "kitchen and dining room": component-skus-kitchen-and-dining-room (parent Component SKUs), kitchen-and-dining-room (parent -)
- "living room": living-room (parent -), component-skus-living-room (parent Component SKUs)
- "mirrored dressers": bedroom-furniture-mirrored-dressers (parent Bedroom Furniture), kids-furniture-mirrored-dressers (parent Kids Furniture)
- "nightstands": kids-furniture-nightstands (parent Kids Furniture), bedroom-furniture-nightstands (parent Bedroom Furniture)
- "outdoor": outdoor (parent -), component-skus-outdoor (parent Component SKUs)
- "storage": entryway-furniture-storage (parent Entryway Furniture), nursery-storage (parent Nursery), kids-furniture-storage (parent Kids Furniture), bedroom-furniture-storage (parent Bedroom Furniture)
- "tables": entryway-furniture-tables (parent Entryway Furniture), patio-furniture-tables (parent Patio Furniture), living-room-tables (parent Living Room)
- "tv stands and media centers": kids-furniture-tv-stands-and-media-centers (parent Kids Furniture), entertainment-tv-stands-and-media-centers (parent Entertainment), bedroom-furniture-tv-stands-and-media-centers (parent Bedroom Furniture)
- "vanities": bedroom-furniture-vanities (parent Bedroom Furniture), kids-furniture-vanities (parent Kids Furniture)
- "washable": blankets-and-throws-washable (parent Blankets and Throws), rugs-washable (parent Rugs)

Candidate leaf options for the router (enabled, leaf, not excluded): **161**

## 2. Products and category links
pim_products: **6834**; with >=1 link in pim_product_categories: **6834**
Link rows whose product is not in pim_products: **0** products
| categories per pim_product | products |
|---|---|
| 1 | 2600 |
| 3 | 3576 |
| 4 | 389 |
| 5 | 82 |
| 6 | 177 |
| 7 | 10 |

Kind of category each existing pim link points to: leaf=7545, parent=8878, excluded=3

pim_products with no usable leaf link: **21**

Store products (not deleted): **36279** (parents/variations: product_type 1 = 10354, simple = 25925)
| categories per store product | products |
|---|---|
| 0 | 2744 |
| 1 | 2600 |
| 2 | 3879 |
| 3 | 24634 |
| 4 | 626 |
| 5 | 1204 |
| 6 | 342 |
| 7 | 74 |
| 8 | 23 |
| 9 | 27 |
| 10 | 33 |
| 11 | 9 |
| 12 | 18 |
| 13 | 8 |
| 14 | 4 |
| 15 | 7 |
| 16 | 5 |
| 17 | 11 |
| 18 | 4 |
| 20 | 3 |
| 21 | 1 |
| 22 | 5 |
| 23 | 3 |
| 24 | 2 |
| 26 | 1 |
| 27 | 1 |
| 28 | 3 |
| 29 | 1 |
| 30 | 2 |
| 33 | 1 |
| 36 | 2 |
| 37 | 2 |

Store products with no category: **2744**; of those, in pim_products: 0, with pim link: 0

## 3. item_code (package signal) in pim_products
| item_code | products |
|---|---|
| Bedroom Package | 1373 |
| Sectional | 569 |
| Bed | 529 |
| Stationary Upholstery Package | 420 |
| Dining Package | 317 |
| Dresser | 204 |
| Vase | 162 |
| Motion Upholstery Package | 148 |
| Table Lamp | 129 |
| Ottoman | 121 |
| Loveseat | 120 |
| Sofa | 120 |
| Pillow | 119 |
| Barstool | 116 |
| Dining Chair | 114 |
| Recliner | 111 |
| Chest | 109 |
| Nightstand | 107 |
| Mirror | 96 |
| End Table | 95 |
| Wall Art | 91 |
| Table Lamp Pair | 81 |
| Rug Large | 78 |
| Chair | 77 |
| Dining Table | 65 |

item_code containing "Package": **2388** products

| category slug linked to packages | links |
|---|---|
| bedroom-sets | 1372 |
| living-room-sets | 664 |
| dining-room-sets | 317 |
| outdoor-sets | 27 |
| home-office-sets | 3 |
| outdoor-package | 2 |
| mattresses-and-bedding-sets | 2 |
| kids-and-nursery-kids-furniture | 1 |
| kids-and-nursery | 1 |
| kids-furniture-beds | 1 |

## 4. pim_raw_items signals
Raw items: 7398 (not deleted: 7398)

| itemType | rows |
|---|---|
| Item | 5194 |
| Component | 2204 |

Distinct itemClass values: **74**
| itemClass | rows |
|---|---|
| CASEGOOD SDG BEDROOM | 969 |
| STAT SDG UPH | 829 |
| CASEGOOD SDG PUR BEDROOM | 421 |
| ACC SDG PUR FLOOR COVER | 386 |
| OUTDOOR SDG PUR FM LIVING | 336 |
| OUTDOOR SDG PUR ACCESSOR | 310 |
| CG SDG PUR MIL BEDROOM | 296 |
| ACC SDG PUR DEC TABLEWARE | 284 |
| CASEGOOD SDG PUR DINING | 265 |
| ACCESSORY SDG PUR LAMPS | 208 |
| ACC SDG PUR DEC WALL ART | 208 |
| ACCESSORY SDG PUR MISC | 204 |
| STAT PUR REPLACEMENTS | 202 |
| ACC SDG PUR THRW/PIL/POUF | 185 |
| RH BEDDING SDG PUR ACCENT | 176 |

itemisPackage values: {None: 7398}
rows with non-empty `categories` text: 0

## 5. pim_vendor_categories -> pim_categories (match by Ashley path)
Rows: 188; vendors: 1; already mapped (pim_category_id set): 0
Exact match on ashley_category: **182**; ambiguous: 0; no match: **6**
Unmatched: Accent Chairs [RUGSANDDECORHOMEACCENTSACCENTCHAIRS]; Mattresses [KIDSANDNURSERYNURSERYMATTRESSES]; Bassinets [KIDSANDNURSERYNURSERYBASSINETS]; Cribs [KIDSANDNURSERYNURSERYCRIBS]; Sheets [KIDSANDNURSERYKIDSBEDDINGSHEETS]; Mattress Pads and Covers [KIDSANDNURSERYKIDSBEDDINGMATTRESSPADSANDCOVERS]