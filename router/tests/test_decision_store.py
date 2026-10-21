import os, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from decision_store import SqlDecisionStore, run_shadow
from contract import RouterInput, RouterOutput

DDL = """
CREATE TABLE router_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, vendor_id TEXT, subject_type TEXT, subject_uuid TEXT, sku TEXT,
  content_hash TEXT, primary_slug TEXT, outcome TEXT, stage TEXT, rule TEXT, confidence REAL, version TEXT, decided_by TEXT,
  status TEXT DEFAULT 'shadow', candidates TEXT, invalidated_reason TEXT);
CREATE TABLE router_review_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, vendor_id TEXT, subject_type TEXT, subject_uuid TEXT, sku TEXT,
  content_hash TEXT, reason TEXT, candidates TEXT, decision_id INTEGER, status TEXT DEFAULT 'open');
"""
def store():
    c = sqlite3.connect(':memory:'); c.executescript(DDL); return SqlDecisionStore(c, '?'), c
def inp(uuid='u1', sku='S1'):
    return RouterInput(vendor_id='ashley', subject_type='raw_item', subject_uuid=uuid, sku=sku, name='Rug')
def out(outcome='assigned', slug='rugs-area-rugs', rule='vendor_path_exact', h='h1', reason=None, stage='rule'):
    return RouterOutput(outcome=outcome, primary_slug=slug, stage=stage, rule=rule, confidence=0.99, version='v1', content_hash=h, review_reason=reason)

def test_shadow_rows_are_not_reused():
    s, _ = store(); s.record(inp(), out())
    assert s.find_reuse('ashley', 'S1', 'h1') is None                      # only 'applied' rows are reused

def test_applied_rows_are_reused_and_human_found():
    s, c = store(); s.record(inp(), out(), status='applied')
    assert s.find_reuse('ashley', 'S1', 'h1') == ('rugs-area-rugs', 0.99)
    s.record(inp('u2', 'S2'), out(stage='human', rule='human', slug='sofas-and-seating-sofas'), status='applied', decided_by='user:7')
    assert s.find_human('ashley', 'raw_item', 'u2') == 'sofas-and-seating-sofas'

def test_new_decision_supersedes_old_live_row_and_history_is_kept():
    s, c = store(); s.record(inp(), out()); s.record(inp(), out(slug='rugs-washable', h='h2'))
    rows = c.execute('SELECT primary_slug, status FROM router_decisions ORDER BY id').fetchall()
    assert rows == [('rugs-area-rugs', 'superseded'), ('rugs-washable', 'shadow')]

def test_review_queue_one_open_row_per_item_and_closed_when_assigned():
    s, c = store()
    s.record(inp(), out('review', None, 'none', reason='below_threshold', stage='review')); s.record(inp(), out('review', None, 'none', reason='below_threshold', stage='review'))
    assert c.execute("SELECT COUNT(*) FROM router_review_queue WHERE status='open'").fetchone()[0] == 1
    s.record(inp(), out())
    assert c.execute("SELECT COUNT(*) FROM router_review_queue WHERE status='open'").fetchone()[0] == 0

def test_invalidate_rule_undoes_only_that_rule_and_version():
    s, c = store(); s.record(inp('u1', 'S1'), out(rule='a')); s.record(inp('u2', 'S2'), out(rule='b'))
    assert s.invalidate_rule('ashley', 'a', 'v1', 'bad rule') == 1
    assert c.execute("SELECT status FROM router_decisions WHERE rule='b'").fetchone()[0] == 'shadow'

def test_run_shadow_counts_and_applies_nothing():
    s, c = store()
    n = run_shadow([inp('u1', 'S1'), inp('u2', 'S2')], lambda i: out() if i.sku == 'S1' else out('review', None, 'none', reason='no_rule_no_model', stage='review'), s)
    assert n == {'assigned': 1, 'review': 1}
    assert c.execute("SELECT COUNT(*) FROM router_decisions WHERE status='applied'").fetchone()[0] == 0
def test_multi_slug_and_uncategorized_roundtrip():
    c = sqlite3.connect(':memory:'); c.executescript(DDL + "ALTER TABLE router_decisions ADD COLUMN slugs TEXT; ALTER TABLE router_decisions ADD COLUMN uncategorized INTEGER DEFAULT 0;")
    s = SqlDecisionStore(c, '?')
    s.record(inp(), RouterOutput('assigned', 'a', 'rule', 'navigable_categories', 0.98, 'v1', 'h1', slugs=['a', 'b']), status='applied')
    assert s.find_reuse('ashley', 'S1', 'h1') == ('a', 0.98, ['a', 'b'])
    s.record(inp('u2', 'S2'), RouterOutput('uncategorized', None, 'rule', 'no_navigable_categories', 0.98, 'v1', 'h2', slugs=[], uncategorized=True))
    assert c.execute("SELECT outcome, slugs, uncategorized FROM router_decisions WHERE sku='S2'").fetchone() == ('uncategorized', '[]', 1)
