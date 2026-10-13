"""contract: input/output shapes, content hash, config loading, output validation.
Vendor-agnostic. Everything vendor-specific comes from vendors/<vendor_id>.yaml."""
import hashlib, json, os, re
from dataclasses import dataclass, field, asdict
from typing import Optional

import yaml

STAGES = ('reuse', 'human', 'rule', 'model', 'review')
REVIEW_REASONS = (
    'no_rule_no_model',      # nothing could decide and the model stage is off
    'none_of_these',         # model said none of the options fit
    'below_threshold',       # model pick under the cutoff, or no cutoff set yet
    'not_offered',           # model answered a slug that was not in its option list
    'inactive',              # category disabled or deleted
    'not_leaf',              # category has children
    'excluded',              # component-skus, uncategorized, store-displays
    'not_in_store',          # exists in master but not synced to the target store
    'contradiction',         # vendor path disagrees with the product name/type
    'no_pool',               # item class has no pool and the all-categories fallback is off
    'review_class',          # item class is configured as review-only (no category fits yet)
)

@dataclass
class RouterInput:
    vendor_id: str
    subject_type: str            # 'raw_item' | 'product'
    subject_uuid: str
    sku: str
    name: str
    description: Optional[str] = None
    item_type: Optional[str] = None
    item_class: Optional[str] = None
    item_code: Optional[str] = None
    vendor_category_path: list = field(default_factory=list)

@dataclass
class RouterOutput:
    outcome: str                 # 'assigned' | 'review'
    primary_slug: Optional[str]
    stage: str
    rule: str
    confidence: Optional[float]
    version: str
    content_hash: str
    review_reason: Optional[str] = None
    candidates: Optional[list] = None

def _norm(s):
    return re.sub(r'\s+', ' ', (s or '').strip()).lower()

def content_hash(inp: RouterInput) -> str:
    """Hash of the fields that can change a decision. Same hash => a past decision can be reused.
    Deliberately excludes uuid/sku (they identify the item, not its content)."""
    payload = {
        'name': _norm(inp.name), 'description': _norm(inp.description),
        'item_type': _norm(inp.item_type), 'item_class': _norm(inp.item_class),
        'item_code': _norm(inp.item_code),
        'vendor_category_path': [_norm(x) for x in (inp.vendor_category_path or [])],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

def load_vendor_config(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    for k in ('vendor_id', 'version', 'field_map', 'settings'):
        if k not in cfg:
            raise ValueError(f'{path}: missing "{k}"')
    cfg['settings'].setdefault('trust_vendor_path', False)
    return cfg

def validate_output(out: RouterOutput, *, allowed_slugs: set, leaf_slugs: set,
                    inactive_slugs: set = frozenset(), excluded_slugs: set = frozenset(),
                    store_slugs: Optional[set] = None) -> list:
    """Returns a list of problems; empty means the output is valid. Code-level safety net
    that applies to every stage, rules included. 'allowed_slugs' = the options this item was offered."""
    errs = []
    if out.stage not in STAGES: errs.append(f'bad stage {out.stage}')
    if out.outcome == 'review':
        if out.primary_slug is not None: errs.append('review must have primary_slug null')
        if out.review_reason not in REVIEW_REASONS: errs.append(f'bad review_reason {out.review_reason}')
        return errs
    if out.outcome != 'assigned': return errs + [f'bad outcome {out.outcome}']
    s = out.primary_slug
    if not s: return errs + ['assigned needs primary_slug']
    if s not in allowed_slugs: errs.append('not_offered')
    if s in inactive_slugs: errs.append('inactive')
    if s in excluded_slugs: errs.append('excluded')
    if s not in leaf_slugs: errs.append('not_leaf')
    if store_slugs is not None and s not in store_slugs: errs.append('not_in_store')
    return errs

def model_decision_ok(confidence: Optional[float], threshold: Optional[float]) -> bool:
    """Fail closed: with no threshold set (Phase 5 not done), a model pick never auto-assigns."""
    return threshold is not None and confidence is not None and confidence >= threshold

def to_dict(obj): return asdict(obj)