-- router-owned tables (MySQL). One copy per tenant/store database.
-- The importer must never write to these, and the router must never write
-- to pim_product_categories directly (Phase 6 decides how decisions get applied).
-- Decisions are append-only: a change is a NEW row; the old one becomes 'superseded'.

CREATE TABLE IF NOT EXISTS router_decisions (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  vendor_id        VARCHAR(64)  NOT NULL,                  -- e.g. 'ashley'
  subject_type     ENUM('raw_item','product') NOT NULL,    -- packages/sets are classified as 'product'
  subject_uuid     VARCHAR(64)  NOT NULL,
  sku              VARCHAR(64)  NOT NULL,
  content_hash     CHAR(64)     NOT NULL,                  -- sha256 of normalized input (see contract.py)
  primary_slug     VARCHAR(255) NULL,                      -- first of slugs; NULL when outcome is review or uncategorized
  slugs            JSON NULL,                              -- every category the product belongs to (a product can be in several)
  uncategorized    TINYINT(1) NOT NULL DEFAULT 0,          -- 1 when the vendor gave no navigable categories
  outcome          ENUM('assigned','review','uncategorized') NOT NULL,
  stage            ENUM('reuse','human','rule','model','review') NOT NULL,
  rule             VARCHAR(64)  NOT NULL,                  -- e.g. vendor_map, package_item_code, vendor_path_exact, model_pool
  confidence       DECIMAL(5,4) NULL,                      -- NULL for rules that have no score
  version          VARCHAR(32)  NOT NULL,                  -- ruleset/config version that produced it
  decided_by       VARCHAR(64)  NOT NULL DEFAULT 'system', -- 'system' or 'user:<id>'
  status           ENUM('shadow','applied','superseded','invalidated') NOT NULL DEFAULT 'shadow',
  candidates       JSON NULL,                              -- options offered + model top 5, for audit
  invalidated_reason VARCHAR(255) NULL,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_reuse    (vendor_id, sku, content_hash, status),   -- cascade step 1 lookup
  KEY idx_subject  (vendor_id, subject_type, subject_uuid),
  KEY idx_rule     (vendor_id, rule, version, status),       -- find/undo everything a bad rule produced
  KEY idx_slug     (primary_slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS router_review_queue (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  vendor_id        VARCHAR(64)  NOT NULL,
  subject_type     ENUM('raw_item','product') NOT NULL,
  subject_uuid     VARCHAR(64)  NOT NULL,
  sku              VARCHAR(64)  NOT NULL,
  content_hash     CHAR(64)     NOT NULL,
  reason           VARCHAR(64)  NOT NULL,                  -- see REVIEW_REASONS in contract.py
  candidates       JSON NULL,                              -- model top 5: [{"slug":..., "p":...}]
  decision_id      BIGINT UNSIGNED NULL,                   -- the router_decisions row that sent it here
  status           ENUM('open','resolved','skipped') NOT NULL DEFAULT 'open',
  resolved_slug    VARCHAR(255) NULL,
  resolved_by      VARCHAR(64)  NULL,
  resolved_at      TIMESTAMP NULL,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_item (vendor_id, subject_type, subject_uuid, content_hash),  -- app must not open a 2nd 'open' row per item
  KEY idx_status (status, vendor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Resolving an item writes a router_decisions row with stage='human', decided_by='user:<id>';
-- that row is what cascade step 2 (earlier human decision) finds next time.
