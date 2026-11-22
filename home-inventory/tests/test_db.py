"""Database tests (owner: Person A).

Each test uses a fresh temporary database file, so the real inventory.db
is never touched.
"""

import os
import sqlite3
import tempfile
import unittest

import db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir.name, "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_path
        self.tmpdir.cleanup()

    # --- initialization ---

    def test_init_creates_tables(self):
        conn = db.connect()
        try:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        finally:
            conn.close()
        self.assertIn("locations", tables)
        self.assertIn("items", tables)

    def test_init_is_safe_to_run_twice(self):
        db.init_db()  # should not raise "table already exists"

    def test_connect_enables_foreign_keys(self):
        conn = db.connect()
        try:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        finally:
            conn.close()

    # --- normalize ---

    def test_normalize_trims_and_casefolds(self):
        self.assertEqual(db.normalize("  Scissors \n"), "scissors")
        self.assertEqual(db.normalize("TAPE Measure"), "tape measure")
        # casefold() handles more than lower(), e.g. German sharp s
        self.assertEqual(db.normalize("STRASSE"), db.normalize("straße"))

    # --- save and get ---

    def test_save_and_get_location(self):
        location_id = db.save_location("Garage / Workbench / Top drawer", ["scissors", "tape measure"])
        location = db.get_location(location_id)
        self.assertEqual(location["id"], location_id)
        self.assertEqual(location["label"], "Garage / Workbench / Top drawer")
        self.assertEqual(location["items"], ["scissors", "tape measure"])

    def test_save_keeps_original_text_for_display(self):
        location_id = db.save_location("  Kitchen / Junk Drawer ", ["  Duct Tape "])
        location = db.get_location(location_id)
        self.assertEqual(location["label"], "Kitchen / Junk Drawer")
        self.assertEqual(location["items"], ["Duct Tape"])

    def test_get_missing_location_returns_none(self):
        self.assertIsNone(db.get_location(9999))

    def test_save_rejects_empty_label(self):
        with self.assertRaises(ValueError):
            db.save_location("   ", ["scissors"])
        self.assertEqual(db.list_locations(), [])

    def test_blank_item_names_are_skipped(self):
        location_id = db.save_location("Shelf", ["", "   ", "marker"])
        self.assertEqual(db.get_location(location_id)["items"], ["marker"])

    # --- duplicates ---

    def test_duplicates_merged_after_normalizing(self):
        location_id = db.save_location("Drawer", ["Scissors", "scissors", " SCISSORS "])
        self.assertEqual(db.get_location(location_id)["items"], ["Scissors"])

    def test_same_item_allowed_in_two_locations(self):
        db.save_location("Garage", ["scissors"])
        db.save_location("Kitchen", ["Scissors"])
        self.assertEqual(len(db.search_items("scissors")), 2)

    def test_unique_constraint_enforced_by_database(self):
        location_id = db.save_location("Drawer", ["scissors"])
        conn = db.connect()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO items (location_id, name, name_norm) VALUES (?, ?, ?)",
                    (location_id, "Scissors", "scissors"),
                )
        finally:
            conn.close()

    # --- foreign keys ---

    def test_item_with_missing_location_is_rejected(self):
        conn = db.connect()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO items (location_id, name, name_norm) VALUES (?, ?, ?)",
                    (9999, "scissors", "scissors"),
                )
        finally:
            conn.close()

    def test_deleting_location_cascades_to_items(self):
        location_id = db.save_location("Drawer", ["scissors", "pliers"])
        conn = db.connect()
        try:
            with conn:
                conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
            count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)

    # --- replace ---

    def test_replace_items(self):
        location_id = db.save_location("Garage", ["scissors", "pliers"])
        db.replace_items(location_id, "Garage / Shelf", ["pliers", "flashlight"])
        location = db.get_location(location_id)
        self.assertEqual(location["label"], "Garage / Shelf")
        self.assertEqual(location["items"], ["pliers", "flashlight"])

    def test_replace_missing_location_raises(self):
        with self.assertRaises(LookupError):
            db.replace_items(9999, "Nowhere", ["scissors"])

    # --- list ---

    def test_list_locations_includes_item_count(self):
        db.save_location("Garage", ["scissors", "pliers"])
        db.save_location("Empty box", [])
        counts = {loc["label"]: loc["item_count"] for loc in db.list_locations()}
        self.assertEqual(counts, {"Garage": 2, "Empty box": 0})

    # --- search ---

    def test_search_is_case_insensitive(self):
        location_id = db.save_location("Garage", ["Scissors"])
        results = db.search_items("SCISSORS")
        self.assertEqual(
            results,
            [{"item": "Scissors", "location_id": location_id, "location_label": "Garage"}],
        )

    def test_search_matches_substring(self):
        db.save_location("Garage", ["tape measure"])
        self.assertEqual(len(db.search_items("tape")), 1)

    def test_search_treats_wildcards_literally(self):
        db.save_location("Garage", ["scissors", "100% cotton rag"])
        self.assertEqual([r["item"] for r in db.search_items("%")], ["100% cotton rag"])
        self.assertEqual(db.search_items("_"), [])

    def test_search_empty_query_returns_nothing(self):
        db.save_location("Garage", ["scissors"])
        self.assertEqual(db.search_items("   "), [])


if __name__ == "__main__":
    unittest.main()
