-- GraphOne / FrontierAtlas — Research Paper vertical slice schema
-- Migration 001: initial schema for arXiv -> GitHub -> Sheets pipeline

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ============================================================
-- LOGICAL IDENTITY: one row per unique arXiv paper
-- ============================================================
CREATE TABLE IF NOT EXISTS papers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arxiv_id        TEXT NOT NULL UNIQUE,
    canonical_url   TEXT NOT NULL,
    title           TEXT,
    authors         JSONB,
    abstract        TEXT,
    published_date  TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'DISCOVERED'
                    CHECK (status IN (
                        'DISCOVERED', 'FETCHED', 'PARSED',
                        'RESOLVING_REPO', 'RESOLVED', 'VALIDATED',
                        'EXPORTED', 'FAILED'
                    )),
    failure_reason  TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_papers_status ON papers (status);

-- ============================================================
-- FETCH OBSERVATIONS: append-only raw evidence, one row per fetch
-- Deliberately NOT unique on source_url — repeated fetches of the
-- same paper are retained, not overwritten, for reproducibility.
-- ============================================================
CREATE TABLE IF NOT EXISTS fetch_observations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id        UUID REFERENCES papers(id),
    source_name     TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    raw_payload     JSONB NOT NULL,
    content_hash    TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    http_status     INT,
    fetch_status    TEXT NOT NULL CHECK (fetch_status IN ('OK', 'ERROR', 'TIMEOUT'))
);

CREATE INDEX IF NOT EXISTS idx_fetch_obs_paper_time ON fetch_observations (paper_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_obs_url_time ON fetch_observations (source_url, fetched_at DESC);

-- ============================================================
-- REPOSITORY ASSOCIATION EVIDENCE
-- 0..N candidate links per paper are legitimate. At most one
-- is_selected=true per paper, enforced by the partial unique index.
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_repo_links (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id            UUID NOT NULL REFERENCES papers(id),
    repo_url            TEXT NOT NULL,
    evidence_type       TEXT NOT NULL CHECK (evidence_type IN (
                            'authoritative_paper_page',
                            'trusted_metadata',
                            'pwc_verified',
                            'pwc_ai_agent_parsed'
                        )),
    evidence_strength   INT NOT NULL CHECK (evidence_strength BETWEEN 1 AND 4),
    evidence_source_url TEXT NOT NULL,
    evidence_locator    TEXT,
    evidence_text       TEXT,
    association_method  TEXT NOT NULL CHECK (association_method IN (
                            'explicit_link_parsed', 'metadata_field', 'pwc_api_field'
                        )),
    observed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_selected         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_repo_links_paper ON paper_repo_links (paper_id);

-- at most one selected repo per paper
CREATE UNIQUE INDEX IF NOT EXISTS one_selected_repo_per_paper
    ON paper_repo_links (paper_id) WHERE is_selected;

-- ============================================================
-- GITHUB SNAPSHOTS: append-only, one row per verification attempt
-- ============================================================
CREATE TABLE IF NOT EXISTS github_repo_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_url            TEXT NOT NULL,
    exists_verified      BOOLEAN NOT NULL,
    stargazers_count    INT,
    stars_fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_status          TEXT NOT NULL CHECK (api_status IN ('OK', 'NOT_FOUND', 'RATE_LIMITED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS idx_gh_snapshots_repo_time ON github_repo_snapshots (repo_url, stars_fetched_at DESC);

-- ============================================================
-- VALIDATED RECORDS: final frozen export-ready payload
-- ============================================================
CREATE TABLE IF NOT EXISTS validated_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id        UUID NOT NULL UNIQUE REFERENCES papers(id),
    schema_version  TEXT NOT NULL DEFAULT '1.0',
    record_type     TEXT NOT NULL DEFAULT 'RESEARCH_PAPER',
    export_payload  JSONB NOT NULL,
    validated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    exported_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_validated_exported ON validated_records (exported_at);

-- ============================================================
-- STRUCTURED PIPELINE LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    stage       TEXT NOT NULL,
    source      TEXT,
    record_id   UUID,
    status      TEXT NOT NULL,
    attempt     INT,
    latency_ms  INT,
    error_type  TEXT,
    provider    TEXT,
    detail      JSONB
);

CREATE INDEX IF NOT EXISTS idx_pipeline_log_stage_ts ON pipeline_log (stage, ts DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_log_record ON pipeline_log (record_id);
