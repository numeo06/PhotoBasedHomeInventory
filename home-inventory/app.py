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


@app.get("/")
def index():
    """Render the home page with saved locations and detector readiness."""
    return render_template(
        "index.html",
        locations=db.list_locations(),
        model=detector.model_status(),
        max_upload_bytes=MAX_UPLOAD_BYTES,
        max_dimension=MAX_DIMENSION,
        upload_field=UPLOAD_FIELD,
    )


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
