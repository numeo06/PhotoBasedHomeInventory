"""Route tests for app.py (owner: Person A).

Uses Flask's test client and a temporary database. The detector is replaced
with unittest.mock for the status-mapping tests, so they run without the
model. One integration test uses the real model and is skipped when the
model files or Transformers are not installed.

Run from home-inventory/:
    python -m unittest tests.test_app -v
"""

import importlib.util
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image

import db

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_tmpdir = None
app_module = None


def setUpModule():
    # Point the database at a temp file BEFORE importing app, because app.py
    # calls db.init_db() at import time.
    global _tmpdir, app_module
    _tmpdir = tempfile.TemporaryDirectory()
    db.DB_PATH = os.path.join(_tmpdir.name, "test.db")
    import app as imported_app

    app_module = imported_app


def tearDownModule():
    _tmpdir.cleanup()


def image_bytes(fmt="PNG", size=(64, 48), color=(200, 120, 90)):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


class ScanRouteTests(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = os.path.join(_tmpdir.name, "test.db")
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def post_photo(self, data, filename="photo.png", field="photo"):
        return self.client.post(
            "/scan",
            data={field: (BytesIO(data), filename)},
            content_type="multipart/form-data",
        )

    def assertInvalid(self, response, reason):
        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertEqual(body["status"], "invalid_file")
        self.assertEqual(body["reason"], reason)
        self.assertEqual(body["items"], [])
        self.assertIsInstance(body["message"], str)

    # ---- page ----

    def test_index_renders_upload_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="photo-input"', html)
        self.assertIn('data-upload-field="photo"', html)
        self.assertIn(f'data-max-bytes="{app_module.MAX_UPLOAD_BYTES}"', html)

    def test_index_escapes_model_detail(self):
        status = {"ready": False, "detail": "<script>alert(1)</script>"}
        with mock.patch.object(app_module.detector, "model_status", return_value=status):
            html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    # ---- validation (detector must not be called) ----

    def test_missing_file_rejected(self):
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.client.post("/scan", data={}, content_type="multipart/form-data")
        self.assertInvalid(response, "missing_file")
        scan.assert_not_called()

    def test_every_rejection_is_logged(self):
        too_big = b"\0" * (app_module.app.config["MAX_CONTENT_LENGTH"] + 1)
        cases = [
            ("missing_file", lambda: self.client.post("/scan", data={}, content_type="multipart/form-data")),
            ("file_too_large", lambda: self.post_photo(too_big)),
            ("unsupported_type", lambda: self.post_photo(b"not an image")),
        ]
        for reason, send in cases:
            with self.subTest(reason=reason), self.assertLogs("app", level="INFO") as logs:
                send()
            self.assertTrue(any(f"reason={reason}" in line for line in logs.output), logs.output)

    def test_wrong_field_name_rejected(self):
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(image_bytes(), field="image")
        self.assertInvalid(response, "missing_file")
        scan.assert_not_called()

    def test_empty_file_rejected(self):
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(b"")
        self.assertInvalid(response, "missing_file")
        scan.assert_not_called()

    def test_text_file_renamed_png_rejected(self):
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(b"just some text, not an image", filename="notes.png")
        self.assertInvalid(response, "unsupported_type")
        scan.assert_not_called()

    def test_gif_rejected_even_though_it_decodes(self):
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(image_bytes("GIF"), filename="photo.png")
        self.assertInvalid(response, "unsupported_type")
        scan.assert_not_called()

    def test_truncated_jpeg_rejected(self):
        data = image_bytes("JPEG", size=(400, 300))
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(data[: len(data) // 2], filename="broken.jpg")
        self.assertInvalid(response, "unsupported_type")
        scan.assert_not_called()

    def test_oversized_file_rejected(self):
        data = image_bytes() + b"\0" * app_module.MAX_UPLOAD_BYTES
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(data)
        self.assertInvalid(response, "file_too_large")
        scan.assert_not_called()

    def test_request_over_body_limit_rejected_as_json(self):
        data = b"\0" * (app_module.app.config["MAX_CONTENT_LENGTH"] + 1)
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(data)
        self.assertInvalid(response, "file_too_large")
        scan.assert_not_called()

    def test_oversized_dimensions_rejected(self):
        too_wide = image_bytes(size=(app_module.MAX_DIMENSION + 1, 8))
        with mock.patch.object(app_module.detector, "scan") as scan:
            response = self.post_photo(too_wide)
        self.assertInvalid(response, "dimensions_too_large")
        scan.assert_not_called()

    def test_max_dimensions_accepted(self):
        exact = image_bytes(size=(app_module.MAX_DIMENSION, 8))
        result = {"status": "no_detections", "items": []}
        with mock.patch.object(app_module.detector, "scan", return_value=result):
            response = self.post_photo(exact)
        self.assertEqual(response.status_code, 200)

    # ---- detector status mapping ----

    def check_status(self, result, http_status, data=None):
        data = data or image_bytes("JPEG")
        with mock.patch.object(app_module.detector, "scan", return_value=result) as scan:
            response = self.post_photo(data, filename="drawer.jpg")
        scan.assert_called_once_with(data)  # the exact validated bytes are passed through
        self.assertEqual(response.status_code, http_status)
        self.assertEqual(response.get_json(), result)  # response passed through unchanged

    def test_ok_returns_200_with_items(self):
        self.check_status({"status": "ok", "items": [{"name": "hammer", "score": 0.231}]}, 200)

    def test_png_accepted(self):
        self.check_status({"status": "ok", "items": []}, 200, data=image_bytes("PNG"))

    def test_no_detections_returns_200(self):
        self.check_status({"status": "no_detections", "items": []}, 200)

    def test_model_unavailable_returns_503(self):
        self.check_status({"status": "model_unavailable", "items": []}, 503)

    def test_scan_error_returns_500(self):
        self.check_status({"status": "scan_error", "items": []}, 500)

    def test_large_upload_never_spools_to_disk(self):
        # Werkzeug normally writes uploads over 500 KB to a temp file. Make any
        # temp-file creation fail, then upload a ~1.5 MB photo.
        import werkzeug.formparser as formparser

        noisy = Image.effect_noise((1200, 1200), 90).convert("RGB")
        buffer = BytesIO()
        noisy.save(buffer, format="PNG")
        data = buffer.getvalue()
        self.assertGreater(len(data), 600 * 1024)

        def no_disk(*_args, **_kwargs):
            raise AssertionError("upload was written to a temporary file")

        with mock.patch.object(formparser, "SpooledTemporaryFile", no_disk), \
                mock.patch.object(formparser, "TemporaryFile", no_disk, create=True):
            self.check_status({"status": "ok", "items": []}, 200, data=data)

    def test_scan_does_not_write_to_database(self):
        before = db.list_locations()
        self.check_status({"status": "ok", "items": [{"name": "hammer", "score": 0.231}]}, 200)
        self.assertEqual(db.list_locations(), before)


class LocationRouteTests(unittest.TestCase):
    """POST /locations, GET/POST /locations/<id>, GET /search (Day 4)."""

    def setUp(self):
        # A fresh database for every test.
        self._counter = getattr(LocationRouteTests, "_counter", 0) + 1
        LocationRouteTests._counter = self._counter
        db.DB_PATH = os.path.join(_tmpdir.name, f"locations_{self._counter}.db")
        db.init_db()
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def create(self, label, items):
        return self.client.post("/locations", json={"label": label, "items": items})

    def assertError(self, response, http_status, fragment=""):
        self.assertEqual(response.status_code, http_status, response.get_data(as_text=True))
        body = response.get_json()
        self.assertIsInstance(body["error"], str)
        self.assertIn(fragment, body["error"])

    # ---- create ----

    def test_create_returns_201_and_saved_location(self):
        response = self.create("  Garage / Workbench / Top drawer ", ["scissors", " tape measure "])
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["label"], "Garage / Workbench / Top drawer")
        self.assertEqual(body["items"], ["scissors", "tape measure"])
        self.assertEqual(db.get_location(body["id"]), body)

    def test_create_merges_duplicates_and_skips_blanks(self):
        body = self.create("Kitchen", ["Scissors", "scissors", " SCISSORS ", "", "  "]).get_json()
        self.assertEqual(body["items"], ["Scissors"])

    def test_create_allows_zero_items(self):
        response = self.create("Empty drawer", [])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["items"], [])

    def test_same_label_twice_creates_two_locations(self):
        first = self.create("Garage", ["hammer"]).get_json()["id"]
        second = self.create("Garage", ["hammer"]).get_json()["id"]
        self.assertNotEqual(first, second)

    # ---- validation ----

    def test_empty_or_blank_label_rejected(self):
        for label in ["", "   ", None, 42]:
            with self.subTest(label=label):
                self.assertError(self.create(label, ["hammer"]), 400, "location name")
        self.assertEqual(db.list_locations(), [])

    def test_label_length_limit(self):
        limit = app_module.MAX_LABEL_LENGTH
        self.assertEqual(self.create("L" * limit, []).status_code, 201)
        self.assertError(self.create("L" * (limit + 1), []), 400, str(limit))

    def test_item_length_limit(self):
        limit = app_module.MAX_ITEM_LENGTH
        self.assertEqual(self.create("Garage", ["x" * limit]).status_code, 201)
        self.assertError(self.create("Garage", ["ok", "x" * (limit + 1)]), 400, "Item 2")

    def test_item_count_limit(self):
        limit = app_module.MAX_ITEMS
        self.assertEqual(self.create("Big bin", [f"item {n}" for n in range(limit)]).status_code, 201)
        self.assertError(self.create("Bigger bin", [f"item {n}" for n in range(limit + 1)]), 400, str(limit))

    def test_bad_body_shapes_rejected(self):
        cases = {
            "items not a list": {"label": "Garage", "items": "hammer"},
            "items missing": {"label": "Garage"},
            "item not text": {"label": "Garage", "items": ["hammer", 3]},
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                self.assertError(self.client.post("/locations", json=body), 400)
        self.assertError(self.client.post("/locations", json=["Garage", ["hammer"]]), 400, "JSON object")
        self.assertError(
            self.client.post("/locations", data="{not json", content_type="application/json"), 400
        )
        self.assertEqual(db.list_locations(), [])

    def test_non_json_request_rejected(self):
        # A plain HTML form post (what another website could send) is refused.
        response = self.client.post("/locations", data={"label": "Garage", "items": "hammer"})
        self.assertError(response, 415, "JSON")

    # ---- load ----

    def test_get_location(self):
        location_id = self.create("Garage", ["hammer", "pliers"]).get_json()["id"]
        response = self.client.get(f"/locations/{location_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"id": location_id, "label": "Garage", "items": ["hammer", "pliers"]})

    def test_get_missing_location_404(self):
        self.assertError(self.client.get("/locations/999"), 404, "999")

    # ---- update ----

    def test_update_replaces_label_and_items(self):
        location_id = self.create("Garage", ["hammer", "scissors"]).get_json()["id"]
        response = self.client.post(
            f"/locations/{location_id}", json={"label": "Garage / Shelf", "items": ["hammer", "Wrench", "wrench"]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(),
                         {"id": location_id, "label": "Garage / Shelf", "items": ["hammer", "Wrench"]})
        self.assertEqual(len(db.list_locations()), 1)  # updated, not duplicated

    def test_update_missing_location_404(self):
        self.assertError(self.client.post("/locations/999", json={"label": "X", "items": []}), 404)

    def test_update_validates_body(self):
        location_id = self.create("Garage", ["hammer"]).get_json()["id"]
        self.assertError(self.client.post(f"/locations/{location_id}", json={"label": " ", "items": []}), 400)
        self.assertEqual(db.get_location(location_id)["items"], ["hammer"])  # unchanged

    # ---- search ----

    def test_search_is_case_insensitive_and_returns_location(self):
        garage = self.create("Garage / Workbench / Top drawer", ["scissors"]).get_json()["id"]
        kitchen = self.create("Kitchen / Junk drawer", ["Scissors"]).get_json()["id"]
        body = self.client.get("/search?q=SCISSORS").get_json()
        self.assertEqual(body["query"], "SCISSORS")
        found = {(r["item"], r["location_id"], r["location_label"]) for r in body["results"]}
        self.assertEqual(found, {
            ("scissors", garage, "Garage / Workbench / Top drawer"),
            ("Scissors", kitchen, "Kitchen / Junk drawer"),
        })

    def test_search_wildcards_are_literal(self):
        self.create("Garage", ["scissors", "100% cotton rag"])
        self.assertEqual([r["item"] for r in self.client.get("/search?q=%25").get_json()["results"]],
                         ["100% cotton rag"])
        self.assertEqual(self.client.get("/search?q=_").get_json()["results"], [])

    def test_empty_search_returns_nothing(self):
        self.create("Garage", ["scissors"])
        for url in ["/search", "/search?q=", "/search?q=%20%20"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["results"], [])

    def test_search_length_limit(self):
        self.assertError(self.client.get("/search?q=" + "a" * (app_module.MAX_QUERY_LENGTH + 1)), 400)

    # ---- the plan's Day 4 acceptance check ----

    def test_acceptance_save_restart_search_edit(self):
        garage = self.create("Garage / Workbench / Top drawer", ["scissors"]).get_json()["id"]
        self.create("Kitchen / Junk drawer", ["Scissors"])

        # "Restart": a brand-new client and a fresh init_db() on the same file.
        db.init_db()
        client = app_module.app.test_client()
        labels = {r["location_label"] for r in client.get("/search?q=SCISSORS").get_json()["results"]}
        self.assertEqual(labels, {"Garage / Workbench / Top drawer", "Kitchen / Junk drawer"})

        reopened = client.get(f"/locations/{garage}").get_json()
        items = [name for name in reopened["items"] if name != "scissors"]
        client.post(f"/locations/{garage}", json={"label": reopened["label"], "items": items})
        labels = [r["location_label"] for r in client.get("/search?q=SCISSORS").get_json()["results"]]
        self.assertEqual(labels, ["Kitchen / Junk drawer"])

    # ---- home page ----

    def test_index_embeds_saved_locations_safely(self):
        self.create("<script>alert(1)</script>", ["a", "b", "c", "d"])
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn('"item_count": 4', html)
        self.assertIn('"preview": ["a", "b", "c"]', html)


def _real_model_available():
    from services import detector

    return detector.model_status()["ready"] and importlib.util.find_spec("transformers") is not None


@unittest.skipUnless(_real_model_available(), "model files or Transformers not installed")
class RealDetectorThroughFlask(unittest.TestCase):
    """End-to-end: a sample photo goes through validation and real inference."""

    def test_sample_photos(self):
        client = app_module.app.test_client()
        expected = {"drawer1.jpg": "dishwasher detergent container", "drawer2.jpg": "hammer"}
        for filename, top_item in expected.items():
            with self.subTest(photo=filename):
                data = (PROJECT_ROOT / "samples" / filename).read_bytes()
                response = client.post(
                    "/scan",
                    data={"photo": (BytesIO(data), filename)},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 200)
                body = response.get_json()
                self.assertEqual(body["status"], "ok")
                self.assertEqual(body["items"][0]["name"], top_item)


if __name__ == "__main__":
    unittest.main()
