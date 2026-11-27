"""Flask app for the Photo-Based Home Inventory (owner: Person A).

Routes call db.py and services/detector.py; they never contain SQL or model
code themselves.
"""

import logging
from io import BytesIO
from time import perf_counter

from flask import Flask, Request, jsonify, render_template, request
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

import db
from services import detector

# Show INFO logs (including the detector's per-scan timing line) in the terminal.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Upload limits (Day 2 decisions, also written in the README).
UPLOAD_FIELD = "photo"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_DIMENSION = 4096  # pixels, per side
ALLOWED_FORMATS = {"JPEG", "PNG"}

# Limits for saved locations (Day 4 decisions, also written in the README).
MAX_LABEL_LENGTH = 200
MAX_ITEM_LENGTH = 100
MAX_ITEMS = 200
MAX_QUERY_LENGTH = 100
PREVIEW_ITEMS = 3  # item names shown on each saved-location card

# HTTP status for each detector status. ok and no_detections are normal results.
SCAN_HTTP_STATUS = {
    "ok": 200,
    "no_detections": 200,
    "model_unavailable": 503,
    "scan_error": 500,
}

class InMemoryUploadRequest(Request):
    """Keep uploaded files in RAM.

    By default Werkzeug spools uploads larger than 500 KB to a temporary file
    on disk. Photos must never touch the disk, so every upload goes into a
    BytesIO instead. MAX_CONTENT_LENGTH below bounds how much memory that uses.
    """

    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return BytesIO()


app = Flask(__name__)
app.request_class = InMemoryUploadRequest
# Hard ceiling for the whole request body. Slightly above the file cap so the
# multipart overhead of a file just under 10 MB is still accepted; the exact
# 10 MB check happens in validate_photo().
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 512 * 1024

# Create the database tables on startup (safe to run every time).
db.init_db()


class InvalidUpload(ValueError):
    """A rejected upload. `reason` is a short machine-readable code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def _invalid(reason: str, message: str, http_status: int = 400):
    return jsonify({"status": "invalid_file", "reason": reason, "message": message, "items": []}), http_status


def validate_photo(data: bytes) -> None:
    """Raise InvalidUpload unless `data` is a decodable JPEG/PNG within the limits.

    The file extension and the browser's content type are never trusted:
    Pillow has to recognise and fully decode the bytes.
    """
    if not data:
        raise InvalidUpload("missing_file", "The uploaded file is empty. Please choose a photo.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidUpload("file_too_large", "The file is larger than 10 MB. Please choose a smaller image.")

    try:
        # Image.open only reads the header, so the size check below runs
        # before any pixels are decoded (protects against decompression bombs).
        with Image.open(BytesIO(data)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise InvalidUpload("unsupported_type", "Only JPEG and PNG images are supported.")
            width, height = image.size
            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                raise InvalidUpload(
                    "dimensions_too_large",
                    f"The image is {width} x {height} pixels. The maximum is "
                    f"{MAX_DIMENSION} x {MAX_DIMENSION}.",
                )
            image.load()  # fully decode: catches truncated or corrupted files
    except InvalidUpload:
        raise
    except Image.DecompressionBombError:
        raise InvalidUpload("dimensions_too_large", "The image has far too many pixels to process.")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise InvalidUpload("unsupported_type", "This file is not a valid JPEG or PNG image.")


class InvalidLocation(ValueError):
    """A rejected location body. Becomes an {"error": message} response."""

    def __init__(self, message: str, http_status: int = 400):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def _error(message: str, http_status: int):
    return jsonify({"error": message}), http_status


def parse_location_body() -> tuple[str, list[str]]:
    """Validate a {"label": str, "items": [str, ...]} JSON body.

    Returns (label, items) with surrounding whitespace trimmed. db.py does
    the normalizing and duplicate merging; this only checks shape and limits.
    """
    if not request.is_json:
        raise InvalidLocation("Send the location as JSON (Content-Type: application/json).", 415)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise InvalidLocation('The body must be a JSON object: {"label": ..., "items": [...]}.')

    label = body.get("label")
    if not isinstance(label, str) or not label.strip():
        raise InvalidLocation("Enter a location name.")
    label = label.strip()
    if len(label) > MAX_LABEL_LENGTH:
        raise InvalidLocation(f"The location name is {len(label)} characters; the limit is {MAX_LABEL_LENGTH}.")

    items = body.get("items")
    if not isinstance(items, list):
        raise InvalidLocation('"items" must be a list of item names.')
    if len(items) > MAX_ITEMS:
        raise InvalidLocation(f"A location can hold at most {MAX_ITEMS} items (got {len(items)}).")
    names = []
    for position, item in enumerate(items, start=1):
        if not isinstance(item, str):
            raise InvalidLocation(f"Item {position} is not text.")
        name = item.strip()
        if len(name) > MAX_ITEM_LENGTH:
            raise InvalidLocation(
                f"Item {position} is {len(name)} characters; item names can be at most {MAX_ITEM_LENGTH}."
            )
        names.append(name)
    return label, names


def location_cards() -> list[dict]:
    """Saved locations for the archive: id, label, item count and a short preview."""
    cards = []
    for row in db.list_locations():
        location = db.get_location(row["id"]) or {"items": []}
        cards.append({
            "id": row["id"],
            "label": row["label"],
            "item_count": row["item_count"],
            "preview": location["items"][:PREVIEW_ITEMS],
        })
    return cards


@app.get("/")
def index():
    """Render the home page with saved locations and detector readiness."""
    return render_template(
        "index.html",
        saved=location_cards(),
        model=detector.model_status(),
        max_upload_bytes=MAX_UPLOAD_BYTES,
        max_dimension=MAX_DIMENSION,
        upload_field=UPLOAD_FIELD,
        limits={
            "label": MAX_LABEL_LENGTH,
            "item": MAX_ITEM_LENGTH,
            "items": MAX_ITEMS,
            "query": MAX_QUERY_LENGTH,
            "preview": PREVIEW_ITEMS,
        },
    )


@app.post("/locations")
def create_location():
    """Create a location and its confirmed items in one transaction."""
    try:
        label, names = parse_location_body()
        location_id = db.save_location(label, names)
    except InvalidLocation as exc:
        return _error(exc.message, exc.http_status)
    except ValueError as exc:  # db.py rejects an empty label
        return _error(str(exc), 400)
    logger.info("Saved new location id=%d items=%d", location_id, len(names))
    return jsonify(db.get_location(location_id)), 201


@app.route("/locations/<int:location_id>", methods=["GET", "POST"])
def location(location_id):
    """GET: load a saved location. POST: replace its label and whole item list."""
    if request.method == "POST":
        try:
            label, names = parse_location_body()
            db.replace_items(location_id, label, names)
        except InvalidLocation as exc:
            return _error(exc.message, exc.http_status)
        except LookupError:
            return _error(f"Location {location_id} does not exist.", 404)
        except ValueError as exc:
            return _error(str(exc), 400)
        logger.info("Updated location id=%d items=%d", location_id, len(names))

    saved = db.get_location(location_id)
    if saved is None:
        return _error(f"Location {location_id} does not exist.", 404)
    return jsonify(saved)


@app.get("/search")
def search():
    """Case-insensitive literal substring search over saved item names."""
    query = request.args.get("q", "").strip()
    if len(query) > MAX_QUERY_LENGTH:
        return _error(f"Search text can be at most {MAX_QUERY_LENGTH} characters.", 400)
    return jsonify({"query": query, "results": db.search_items(query)})


@app.post("/scan")
def scan():
    """Validate one uploaded photo, run the detector, return its JSON.

    The photo is only held in memory for this request. Nothing is written to
    disk or the database.
    """
    upload = request.files.get(UPLOAD_FIELD)
    if upload is None or not upload.filename:
        logger.info("Rejected upload reason=missing_file")
        return _invalid("missing_file", "No photo was uploaded. Please choose a photo.")

    data = upload.read(MAX_UPLOAD_BYTES + 1)
    try:
        validate_photo(data)
    except InvalidUpload as exc:
        logger.info("Rejected upload reason=%s bytes=%d", exc.reason, len(data))
        return _invalid(exc.reason, exc.message)

    started = perf_counter()
    result = detector.scan(data)
    logger.info(
        "POST /scan status=%s elapsed_ms=%.1f items=%d",
        result.get("status"),
        (perf_counter() - started) * 1000,
        len(result.get("items", [])),
    )
    return jsonify(result), SCAN_HTTP_STATUS.get(result.get("status"), 500)


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_exc):
    """The request body is over MAX_CONTENT_LENGTH: answer in the /scan JSON shape."""
    logger.info("Rejected upload reason=file_too_large content_length=%s", request.content_length)
    return _invalid("file_too_large", "The file is larger than 10 MB. Please choose a smaller image.")
