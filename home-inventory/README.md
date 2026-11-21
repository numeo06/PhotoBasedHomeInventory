# Photo-Based Home Inventory

A local web app that answers "where did I put that?" Upload a photo of a drawer,
toolbox, shelf or garage bin; a local OWL-ViT object detector suggests the items
it sees; you review, rename, remove or add items; and the confirmed list is saved
under a location in SQLite so you can search for it later. The AI runs on your own
computer, so no API key is needed.

**Team:** Person A (screens + database), Person B (model + packaging). Replace these with your names.

## Technology stack

- Python 3.11
- Flask + Jinja templates
- SQLite (Python's built-in `sqlite3`)
- HTML, CSS, vanilla JavaScript (no frontend frameworks)
- Pillow (image validation)
- Later, added by Person B: CPU PyTorch, Transformers, `google/owlvit-base-patch32`

## Project structure

```
home-inventory/
    app.py               Flask app and routes                        [A]
    db.py                connections, transactions, save/load/search [A]
    schema.sql           locations and items tables                  [A]
    requirements.txt     pinned dependencies                         [B adds model deps]
    templates/index.html home page                                   [A]
    static/app.js        frontend interactions                       [A]
    static/style.css     styling                                     [A]
    services/detector.py model_status() and scan() (stub for now)    [B]
    config/labels.json   target labels and score threshold           [B]
    scripts/setup_model.py  one-time model download (placeholder)    [B]
    samples/             safe demo photos                            [B]
    models/              downloaded weights (git-ignored)            [B]
    tests/test_contract.py  detector interface shape                 [both]
    tests/test_db.py     database behaviour                          [A]
    tests/test_detector.py  sample-photo tests (placeholder)         [B]
```

## Setup (Windows, PowerShell)

Run these from the `home-inventory` folder.

```powershell
# 1. Create the virtual environment with Python 3.11 (one time)
py -3.11 -m venv .venv

# 2. Activate it (do this in every new terminal)
.venv\Scripts\Activate.ps1
#    If PowerShell blocks the script, run this once, then activate again:
#    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3. Install dependencies
python -m pip install -r requirements.txt

# 4. Check the version: should print Python 3.11.x
python --version
```

macOS or Linux: `python3.11 -m venv .venv`, then `source .venv/bin/activate`.

## Run the app

```powershell
python -m flask --app app run
```

Open http://127.0.0.1:5000. The database file `inventory.db` is created
automatically on first start. Stop the server with Ctrl+C.

## Run the tests

```powershell
python -m unittest discover tests -v
```

Tests use a temporary database, so they never touch `inventory.db`.

## Interfaces agreed between A and B

```
detector.model_status() -> {"ready": bool, "detail": str}
detector.scan(image_bytes) -> {"status": "ok" | "no_detections" | "model_unavailable" | "scan_error",
                               "items": [{"name": str, "score": float}]}
```

`scan()` never raises. The score is a detector score, not a probability.

## Day 1 decisions

- Two locations **may** share the same label; only item names must be unique within a location.
- Item names that match after trimming and casefolding are merged; the first spelling is kept for display.
- Blank item names are skipped. An empty location label is rejected (`ValueError`).
- `replace_items` raises `LookupError` if the location id does not exist.
- Search is a literal, case-insensitive substring match using `instr()`, so `%` and `_` are plain characters.
- Still to decide: the upload size cap, max image dimensions and HTTP codes for scan failures (Day 2).

## What is stored

Locations (label, timestamps) and confirmed item names. Photos are never stored.

## Current limitations (Day 1)

- The home page is a placeholder: no upload, review, save or search UI yet.
- Only `GET /` exists. `POST /scan`, `/locations` and `/search` come on Days 2 to 4.
- The detector is a stub that returns fake suggestions; the real OWL-ViT model is not installed.
- `scripts/setup_model.py` and `tests/test_detector.py` are placeholders for Person B.
