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

## Day 2 decisions: `POST /scan`

- Multipart field name: `photo`. One JPEG or PNG, at most **10 MB** and **4096 x 4096 px**.
- The server checks the type by decoding the file with Pillow (header, format, size, then a full decode),
  never by trusting the extension or the browser's content type. GIF, WebP, HEIC and corrupted files are rejected.
- The photo stays in memory: uploads are never spooled to a temp file, written to disk or saved in the database.
- Responses (the detector's JSON is passed through unchanged):

| Case | HTTP | Body |
|---|---|---|
| Suggestions found | 200 | `{"status": "ok", "items": [{"name", "score"}]}` |
| Nothing above threshold | 200 | `{"status": "no_detections", "items": []}` |
| Model files missing | 503 | `{"status": "model_unavailable", "items": []}` |
| Inference or loading failed | 500 | `{"status": "scan_error", "items": []}` |
| Rejected upload | 400 | `{"status": "invalid_file", "reason": ..., "message": ..., "items": []}` |

  `reason` is one of `missing_file`, `file_too_large`, `unsupported_type`, `dimensions_too_large`.
  `invalid_file` comes from the route's validation only; `detector.scan()` keeps its four statuses.
- Each scan logs its elapsed time in the Flask terminal.

## What is stored

Locations (label, timestamps) and confirmed item names. Photos are never stored.

## Current limitations (Day 2)

- Saving, reopening and searching locations (`/locations`, `/search`) come on Day 4. The upload page
  has no Save button yet, and History, Settings and Help are marked "soon".
- The detector only suggests labels from `config/labels.json`; everything else is added by hand.
# PhotoBasedHomeInventory
Local web app that answers “where did I put that?”: upload a drawer photo, review AI-suggested items from an on-device OWL-ViT model, save them to SQLite, and search by keyword. No API key needed.

## Local setup on Windows

Create the virtual environment and install dependencies from the Git repository root in PowerShell. The model setup and sample checks run from the `home-inventory` app directory.

- Python 3.11 is required. Tested with Python 3.11.9, PyTorch 2.9.1+cpu, TorchVision 0.24.1, and Transformers 4.57.1.
- Internet access is required for initial setup. The detector runs locally after setup and requires no API key.

### 1. Clone the repository

Clone the repository using **Code > HTTPS** on GitHub, or download and extract the ZIP. Open PowerShell in `PhotoBasedHomeInventory` and check your Python version.

```powershell
py -3.11 --version
```

If Python 3.11 is missing, install it alongside any existing Python version. With the [Python Install Manager](https://www.python.org/downloads/windows/), run `pymanager install 3.11`.

### 2. Create the virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe --version
```

If the legacy `py` launcher does not see the Python Install Manager's copy of 3.11, use `pymanager exec -V:3.11 -m venv .venv` for the first line. The version check should print Python 3.11.x. If the repository already has a working `.venv`, reuse it.

### 3. Install CPU dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install "transformers==4.57.1" Pillow
.\.venv\Scripts\python.exe -m pip check
```

The final command should report `No broken requirements found`.

### 4. Download the model once

```powershell
Set-Location .\home-inventory
..\.venv\Scripts\python.exe .\scripts\setup_model.py
```

The script downloads the pinned public snapshot to `home-inventory/models/owlvit-base-patch32/`, including about 613 MB of weights. Wait for `Model ready:` and the revision output. If you already have the snapshot in the repo-root `models/` directory, you can copy `owlvit-base-patch32/` into `home-inventory/models/` and skip the download. Git ignores the root `.venv/` and both model directories.

### 5. Run the sample scan

From `home-inventory/`, run:

```powershell
..\.venv\Scripts\python.exe -m tests.scan_samples
```

The check scans both committed drawer photos in one process and prints the JSON response for each using the default threshold of `0.12`.

For the timing CLI, run:

```powershell
..\.venv\Scripts\python.exe .\scripts\test_owlvit.py .\samples\drawer1.jpg .\samples\drawer1.jpg .\samples\drawer2.jpg --threshold 0.12
```

The script prints model load time, cold load plus first scan, per-photo elapsed times, and item suggestions with detector scores. The repeated first image measures a warm run on the same input. You can change the score filter with `--threshold`. This check runs independently of Flask.
