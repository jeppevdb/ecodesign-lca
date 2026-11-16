"""SQLite layout of a project file.

A project stores references to datasets only – never impact factors.
"""

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL              -- JSON
);

CREATE TABLE stage (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE COLLATE NOCASE,
    role     TEXT,                   -- see classifications.STAGE_ROLES; NULL = user-defined
    position INTEGER NOT NULL
);
CREATE UNIQUE INDEX stage_role ON stage(role) WHERE role IS NOT NULL;

CREATE TABLE market (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT
);

-- An uploaded impact-factor file ('process') or characterisation-factor list ('flow').
CREATE TABLE database (
    id        INTEGER PRIMARY KEY,
    kind      TEXT NOT NULL CHECK (kind IN ('process', 'flow')),
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    version   TEXT,
    protocol  TEXT,
    file_hash TEXT,
    coverage  TEXT NOT NULL DEFAULT '{}'   -- JSON: {"derived": bool, "missing_categories": [...]}
);

-- A dataset or elementary flow used somewhere in the project.
-- name/unit/location are cached for display; 'missing' is set when the
-- dataset can no longer be found in its database.
CREATE TABLE dataset_ref (
    id          INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL REFERENCES database(id),
    dataset_key TEXT NOT NULL,
    name        TEXT NOT NULL,
    unit        TEXT NOT NULL,
    location    TEXT,
    relink_key  TEXT,                -- version-independent code, if the database has one
    missing     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (database_id, dataset_key)
);

CREATE TABLE pathway (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('supplier', 'gate_to_customer', 'eol')),
    name        TEXT NOT NULL COLLATE NOCASE,
    description TEXT,
    market_id   INTEGER REFERENCES market(id) ON DELETE CASCADE,  -- gate_to_customer only
    UNIQUE (kind, name)
);
CREATE UNIQUE INDEX pathway_gate_market ON pathway(market_id) WHERE kind = 'gate_to_customer';

-- supplier / gate_to_customer: amount is a distance, dataset is a transport service.
-- eol: amount is the share of the weight (kg per kg) sent to the treatment dataset;
--      market_id NULL means the leg applies in every market.
CREATE TABLE pathway_leg (
    id             INTEGER PRIMARY KEY,
    pathway_id     INTEGER NOT NULL REFERENCES pathway(id) ON DELETE CASCADE,
    market_id      INTEGER REFERENCES market(id) ON DELETE CASCADE,
    position       INTEGER NOT NULL DEFAULT 0,
    dataset_ref_id INTEGER REFERENCES dataset_ref(id),
    amount         REAL,
    unit           TEXT,
    note           TEXT,
    ghg_category   TEXT,
    en15804_module TEXT,
    ped_reliability   INTEGER,
    ped_completeness  INTEGER,
    ped_temporal      INTEGER,
    ped_geographical  INTEGER,
    ped_technological INTEGER
);

-- parent_id NULL and alternative_of NULL: the product (exactly one).
-- alternative_of set: this node (with everything below it) is a design
-- alternative that replaces the referenced base node. It shares the base
-- node's parent.
CREATE TABLE node (
    id              INTEGER PRIMARY KEY,
    parent_id       INTEGER REFERENCES node(id) ON DELETE CASCADE,
    alternative_of  INTEGER REFERENCES node(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL DEFAULT 0,
    name            TEXT NOT NULL,
    quantity        REAL NOT NULL DEFAULT 1 CHECK (quantity > 0),
    level_label     TEXT,
    internal_number TEXT,
    description     TEXT,
    price           REAL,
    weight          REAL,            -- kg
    weight_is_total INTEGER NOT NULL DEFAULT 0,
    production_site TEXT CHECK (production_site IN ('on_site', 'supplier')),
    supplier_pathway_id       INTEGER REFERENCES pathway(id),
    supplier_exclusion_reason TEXT,
    eol_mode        TEXT CHECK (eol_mode IN ('whole', 'split', 'excluded')),
    eol_pathway_id            INTEGER REFERENCES pathway(id),
    eol_exclusion_reason      TEXT,
    eol_own_pathway_id        INTEGER REFERENCES pathway(id),
    eol_own_exclusion_reason  TEXT,
    has_use_inputs  INTEGER NOT NULL DEFAULT 0,
    alt_label             TEXT,
    alt_short_description TEXT,
    alt_long_description  TEXT,
    is_removed      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX node_parent ON node(parent_id);
CREATE INDEX node_alternative ON node(alternative_of);

CREATE TABLE entry (
    id             INTEGER PRIMARY KEY,
    node_id        INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    type           TEXT NOT NULL,
    stage_id       INTEGER REFERENCES stage(id),
    position       INTEGER NOT NULL DEFAULT 0,
    description    TEXT,
    dataset_ref_id INTEGER REFERENCES dataset_ref(id),
    amount         REAL,
    unit           TEXT,
    amount_note    TEXT,
    exclusion_reason TEXT,
    ghg_category   TEXT,
    en15804_module TEXT,
    ped_reliability   INTEGER,
    ped_completeness  INTEGER,
    ped_temporal      INTEGER,
    ped_geographical  INTEGER,
    ped_technological INTEGER
);
CREATE INDEX entry_node ON entry(node_id);

-- Use entries: one dataset per market, sharing the entry's amount.
CREATE TABLE entry_market_dataset (
    entry_id       INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    market_id      INTEGER NOT NULL REFERENCES market(id) ON DELETE CASCADE,
    dataset_ref_id INTEGER NOT NULL REFERENCES dataset_ref(id),
    PRIMARY KEY (entry_id, market_id)
);

CREATE TABLE scenario (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT
);

-- Multipliers; the average case is always 1.
CREATE TABLE parameter (
    id          INTEGER PRIMARY KEY,
    scenario_id INTEGER NOT NULL REFERENCES scenario(id) ON DELETE CASCADE,
    name        TEXT NOT NULL COLLATE NOCASE,
    best        REAL,
    worst       REAL,
    assumption_best    TEXT,
    assumption_average TEXT,
    assumption_worst   TEXT,
    UNIQUE (scenario_id, name)
);

CREATE TABLE parameter_link (
    id           INTEGER PRIMARY KEY,
    parameter_id INTEGER NOT NULL REFERENCES parameter(id) ON DELETE CASCADE,
    target_type  TEXT NOT NULL CHECK (target_type IN ('entry', 'pathway_leg', 'node_weight', 'node_price')),
    target_id    INTEGER NOT NULL,
    UNIQUE (parameter_id, target_type, target_id)
);

CREATE TRIGGER entry_links AFTER DELETE ON entry BEGIN
    DELETE FROM parameter_link WHERE target_type = 'entry' AND target_id = OLD.id;
END;
CREATE TRIGGER leg_links AFTER DELETE ON pathway_leg BEGIN
    DELETE FROM parameter_link WHERE target_type = 'pathway_leg' AND target_id = OLD.id;
END;
CREATE TRIGGER node_links AFTER DELETE ON node BEGIN
    DELETE FROM parameter_link
    WHERE target_type IN ('node_weight', 'node_price') AND target_id = OLD.id;
END;

-- Named combinations of alternatives (interface comes later). The base design
-- and "one alternative at a time" designs are derived, not stored.
CREATE TABLE design (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT
);
CREATE TABLE design_substitution (
    design_id           INTEGER NOT NULL REFERENCES design(id) ON DELETE CASCADE,
    base_node_id        INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    alternative_node_id INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    PRIMARY KEY (design_id, base_node_id)
);
"""
