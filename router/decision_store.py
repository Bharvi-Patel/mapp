"""Phase 6: the router's decision tables (contract/schema.sql) as a store for route(), plus shadow mode.

Rules this module keeps:
  * It writes ONLY router_decisions and router_review_queue. It never touches pim_product_categories.
  * Decisions are append-only. A changed decision is a new row; the old live row becomes 'superseded'.
  * Shadow mode records what the router WOULD do (status 'shadow'). Nothing is applied.
  * Step 0/1 reuse only trusts rows with status 'applied', so shadow runs never feed themselves.
  * Any rule/version that turns out bad can be found and switched off with invalidate_rule().
conn is a DB-API connection (pymysql / mysql.connector). paramstyle is '%s' for MySQL, '?' for sqlite (tests).
"""
import json

LIVE = ('shadow', 'applied')

class SqlDecisionStore:
    def __init__(self, conn, paramstyle='%s'):
        self.conn, self.ph = conn, paramstyle
        try: self._q("SELECT slugs, uncategorized FROM router_decisions WHERE 1=0"); self.multi = True    # table has the multi-category columns
        except Exception:
            self.multi = False                                                                          # older table: single primary_slug only
            try: self.conn.rollback()
            except Exception: pass

    def _q(self, sql, params=()):
        cur = self.conn.cursor(); cur.execute(sql.replace('%s', self.ph), params); return cur

    # ---- lookups used by route() steps 0 and 1 -------------------------------------------------------------
    def find_reuse(self, vendor, sku, chash):
        cols = "primary_slug, confidence, slugs" if self.multi else "primary_slug, confidence"
        r = self._q(f"SELECT {cols} FROM router_decisions WHERE vendor_id=%s AND sku=%s AND content_hash=%s "
                    "AND status='applied' AND outcome='assigned' ORDER BY id DESC LIMIT 1", (vendor, sku, chash)).fetchone()
        if not r: return None
        conf = float(r[1]) if r[1] is not None else 1.0
        slugs = json.loads(r[2]) if self.multi and r[2] else None
        return (r[0], conf, slugs) if slugs and len(slugs) > 1 else (r[0], conf)      # several categories: hand them all back

    def find_human(self, vendor, subject_type, uuid):
        r = self._q("SELECT primary_slug FROM router_decisions WHERE vendor_id=%s AND subject_type=%s AND subject_uuid=%s "
                    "AND stage='human' AND status='applied' AND outcome='assigned' ORDER BY id DESC LIMIT 1",
                    (vendor, subject_type, uuid)).fetchone()
        return r[0] if r else None

    # ---- writing -------------------------------------------------------------------------------------------
    def record(self, inp, out, status='shadow', decided_by='system'):
        """Append one decision. Returns its id. Older live rows for the same item are marked superseded."""
        self._q("UPDATE router_decisions SET status='superseded' WHERE vendor_id=%s AND subject_type=%s AND subject_uuid=%s "
                "AND status IN ('shadow','applied') AND status=%s", (inp.vendor_id, inp.subject_type, inp.subject_uuid, status))
        cur = self._q("INSERT INTO router_decisions (vendor_id, subject_type, subject_uuid, sku, content_hash, primary_slug, outcome, "
                      "stage, rule, confidence, version, decided_by, status, candidates) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (inp.vendor_id, inp.subject_type, inp.subject_uuid, inp.sku, out.content_hash, out.primary_slug, out.outcome,
                       out.stage, out.rule or out.stage, out.confidence, out.version, decided_by, status,
                       json.dumps(out.candidates) if out.candidates is not None else None))
        if self.multi: self._q("UPDATE router_decisions SET slugs=%s, uncategorized=%s WHERE id=%s", (json.dumps(out.slugs or []), 1 if out.uncategorized else 0, cur.lastrowid))
        did = cur.lastrowid
        if out.outcome == 'review': self._open_review(inp, out, did)
        else: self._close_reviews(inp)
        self.conn.commit()
        return did

    def _open_review(self, inp, out, decision_id):
        exists = self._q("SELECT id FROM router_review_queue WHERE vendor_id=%s AND subject_type=%s AND subject_uuid=%s "
                         "AND content_hash=%s AND status='open'", (inp.vendor_id, inp.subject_type, inp.subject_uuid, out.content_hash)).fetchone()
        if exists: return                                                      # never a second open row for one item
        self._q("INSERT INTO router_review_queue (vendor_id, subject_type, subject_uuid, sku, content_hash, reason, candidates, decision_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (inp.vendor_id, inp.subject_type, inp.subject_uuid, inp.sku, out.content_hash,
                 out.review_reason or 'unknown', json.dumps(out.candidates) if out.candidates is not None else None, decision_id))

    def _close_reviews(self, inp):
        self._q("UPDATE router_review_queue SET status='skipped' WHERE vendor_id=%s AND subject_type=%s AND subject_uuid=%s AND status='open'",
                (inp.vendor_id, inp.subject_type, inp.subject_uuid))

    def invalidate_rule(self, vendor, rule, version, reason):
        """Undo everything one rule produced in one ruleset version. Returns the number of rows changed."""
        cur = self._q("UPDATE router_decisions SET status='invalidated', invalidated_reason=%s WHERE vendor_id=%s AND rule=%s "
                      "AND version=%s AND status IN ('shadow','applied')", (reason, vendor, rule, version))
        self.conn.commit(); return cur.rowcount

    def counts_by_rule(self, vendor, version):
        return self._q("SELECT rule, outcome, COUNT(*) FROM router_decisions WHERE vendor_id=%s AND version=%s AND status IN ('shadow','applied') "
                       "GROUP BY rule, outcome ORDER BY rule", (vendor, version)).fetchall()


def run_shadow(inputs, route_fn, store, status='shadow'):
    """Route every input and record the decision. route_fn(inp) -> RouterOutput. Nothing is applied anywhere."""
    n = {'assigned': 0, 'review': 0}
    for inp in inputs:
        out = route_fn(inp); store.record(inp, out, status=status); n[out.outcome] = n.get(out.outcome, 0) + 1
    return n