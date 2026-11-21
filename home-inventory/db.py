"""Database layer for the home inventory (owner: Person A).

All SQL lives in this file. Flask routes call these functions and never
write SQL themselves. Every query uses ? placeholders (parameterized SQL).
"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# The database file sits next to this file. Tests point this at a temp file.
DB_PATH = os.path.join(BASE_DIR, "inventory.db")


def connect() -> sqlite3.Connection:
    """Open a connection with foreign keys turned on.

    SQLite turns foreign keys OFF by default and the setting is per
    connection, so we must enable it every time we connect.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["label"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the tables from schema.sql if they do not exist yet."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = f.read()
    conn = connect()
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def normalize(text: str) -> str:
    """Trim whitespace and casefold, so "  Scissors " matches "scissors"."""
    return text.strip().casefold()


def _clean_names(names: list[str]) -> list[tuple[str, str]]:
    """Return (display, normalized) pairs, dropping blanks and duplicates.

    When two names normalize to the same text ("Scissors" and "scissors"),
    the first one wins and its original spelling is kept for display.
    """
    seen = set()
    cleaned = []
    for name in names:
        display = name.strip()
        norm = normalize(name)
        if norm and norm not in seen:
            seen.add(norm)
            cleaned.append((display, norm))
    return cleaned


def _clean_label(label: str) -> tuple[str, str]:
    """Return (display, normalized) for a location label. Rejects empty labels."""
    display = label.strip()
    if not display:
        raise ValueError("Location label cannot be empty.")
    return display, normalize(label)


def _insert_items(conn: sqlite3.Connection, location_id: int, names: list[str]) -> None:
    conn.executemany(
        "INSERT INTO items (location_id, name, name_norm) VALUES (?, ?, ?)",
        [(location_id, display, norm) for display, norm in _clean_names(names)],
    )


def save_location(label: str, names: list[str]) -> int:
    """Create a location and its confirmed items in one transaction.

    Returns the new location id. Raises ValueError if the label is empty.
    Duplicate names (after normalizing) are merged into one item.
    """
    display, norm = _clean_label(label)
    conn = connect()
    try:
        with conn:  # commits on success, rolls back on any error
            cur = conn.execute(
                "INSERT INTO locations (label, label_norm) VALUES (?, ?)",
                (display, norm),
            )
            location_id = cur.lastrowid
            _insert_items(conn, location_id, names)
        return location_id
    finally:
        conn.close()


def get_location(location_id: int) -> dict | None:
    """Return {"id", "label", "items": [display names]} or None if not found."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, label FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            return None
        items = conn.execute(
            "SELECT name FROM items WHERE location_id = ? ORDER BY id",
            (location_id,),
        ).fetchall()
        return {"id": row["id"], "label": row["label"], "items": [r["name"] for r in items]}
    finally:
        conn.close()


def replace_items(location_id: int, label: str, names: list[str]) -> None:
    """Replace a location's label and whole item list in one transaction.

    Raises ValueError if the label is empty and LookupError if the
    location does not exist.
    """
    display, norm = _clean_label(label)
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE locations SET label = ?, label_norm = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (display, norm, location_id),
            )
            if cur.rowcount == 0:
                raise LookupError(f"Location {location_id} does not exist.")
            conn.execute("DELETE FROM items WHERE location_id = ?", (location_id,))
            _insert_items(conn, location_id, names)
    finally:
        conn.close()


def list_locations() -> list[dict]:
    """Return every location with its item count, newest update first."""
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT locations.id, locations.label, COUNT(items.id) AS item_count
            FROM locations
            LEFT JOIN items ON items.location_id = locations.id
            GROUP BY locations.id
            ORDER BY locations.updated_at DESC, locations.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def search_items(query: str) -> list[dict]:
    """Find items whose name contains the query (case-insensitive, literal).

    Uses instr() instead of LIKE so that % and _ in the query are treated
    as plain characters, not wildcards. An empty query returns no results.
    """
    needle = normalize(query)
    if not needle:
        return []
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT items.name AS item,
                   locations.id AS location_id,
                   locations.label AS location_label
            FROM items
            JOIN locations ON locations.id = items.location_id
            WHERE instr(items.name_norm, ?) > 0
            ORDER BY locations.label, items.name
            """,
            (needle,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
