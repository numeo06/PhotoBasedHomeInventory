-- schema.sql: tables for the Photo-Based Home Inventory.
-- Run by db.init_db() on startup. "IF NOT EXISTS" makes it safe to run every time.

CREATE TABLE IF NOT EXISTS locations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,                       -- display text as the user typed it
    label_norm  TEXT NOT NULL,                       -- trimmed + casefolded
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id  INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,                      -- display text as the user typed it
    name_norm    TEXT NOT NULL,                      -- trimmed + casefolded, used for matching
    UNIQUE (location_id, name_norm)
);

CREATE INDEX IF NOT EXISTS idx_items_name_norm ON items(name_norm);
