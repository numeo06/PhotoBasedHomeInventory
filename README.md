# Photo-Based Home Inventory (SnapSort)

**Students:** Branda Heng (Role A) and Carter McDonald (Role B).

Scan a photo of a drawer to get suggested item names. Rename or remove incorrect suggestions, add missing items by hand, and save the corrected list under a location. Search by item name later to find where you put it. SQLite stores the location and confirmed items. Uploaded photos stay in memory during the scan.

## Technology stack

- Python 3.11 (3.11.9 in the local environment), Flask 3.1.3 with Jinja, HTML, CSS, and vanilla JavaScript.
- SQLite through Python's built-in `sqlite3` module (SQLite 3.45.1 in the local environment).
- Pillow 13.0.0 for image validation and preparation.
- CPU PyTorch 2.9.1+cpu, TorchVision 0.24.1+cpu, and Transformers 4.57.1 for local inference. `huggingface-hub` 0.36.2 handles the one-time model download. [Pinned dependencies](home-inventory/requirements.txt)
- Local OWL-ViT base patch32 (`google/owlvit-base-patch32`), pinned to revision `cbc355fb364588351c5d51c7f74465e8e7ec6f72`. The detector loads the processor and Safetensors weights from disk and runs inference on the CPU. [Model setup script](home-inventory/scripts/setup_model.py)

## Setup and run on Windows (PowerShell)

Internet access is needed to clone the repository, install Python and dependencies, and download the model once. After setup, the app and detector use local files and services. No API key is required.

### 1. Clone and create the environment

From the parent folder where you want the checkout, run the following. Install Python 3.11 first if the launcher cannot find it.

```powershell
git clone https://github.com/numeo06/PhotoBasedHomeInventory.git
Set-Location .\PhotoBasedHomeInventory
py -3.11 --version
py -3.11 -m venv .venv
```

The remaining commands call the virtual environment's Python directly, so activation is optional.

### 2. Install dependencies

Run these commands from the repository root (`PhotoBasedHomeInventory`).

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\home-inventory\requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

The requirements file includes the PyTorch CPU wheel index. The last command should report `No broken requirements found`.

### 3. Download the model once

From the repository root, enter the app folder and run the setup script.

```powershell
Set-Location .\home-inventory
..\.venv\Scripts\python.exe .\scripts\setup_model.py
```

The script writes the snapshot to `home-inventory/models/owlvit-base-patch32/` and prints `Model ready:` and the pinned revision when the required files are present.

### 4. Start Flask and open the app

Run this command from the `home-inventory` app folder.

```powershell
..\.venv\Scripts\python.exe -m flask --app app run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Flask creates `home-inventory/inventory.db` on first startup. Stop the server with Ctrl+C. On later runs, open PowerShell in `PhotoBasedHomeInventory\home-inventory` and repeat only the Flask command.

### Verification commands

From `home-inventory`, run the unit suite and scan both committed drawer photos. The last command compares model load and first-scan time with later scans.

```powershell
..\.venv\Scripts\python.exe -m unittest discover tests -v
..\.venv\Scripts\python.exe -m tests.scan_samples
..\.venv\Scripts\python.exe .\scripts\test_owlvit.py .\samples\drawer1.jpg .\samples\drawer1.jpg .\samples\drawer2.jpg --threshold 0.12
```

Using the existing Windows environment and downloaded model, `pip check` passed, 66 tests passed with one skipped, and both standalone sample scans returned `ok`.

## Individual contributions

**Num (Role A).** Built the upload and preview UI, editable item list, and validated Flask scan route that calls the detector. Built the SQLite inventory layer and the browser workflow for saving, reopening, updating, and searching inventories. Recorded the Day 3 scan and upload checks and the Day 4 browser save and search check. [Day 1 notes](DAY1_NOTES.txt), [Day 3 test results](DAY3_TEST_RESULTS.txt), [Day 4 notes](DAY4_NOTES.txt)

**Carter (Role B).** Set up the pinned OWL-ViT download and CPU inference, integrated the detector into the app's service interface, and added sample photos, a smoke check, and a timing script for detector verification. Carter also committed fixes for delayed save and scan responses in `162a137`, preserving newer editor changes and discarding stale scan results after a photo change. That commit is on `b/day4-editor-fixes` and is absent from the current `main`. Carter repeated the delayed-response checks in the browser. **Before submission:** Confirm whether the submission should include the fix.

See the [team reflection](REFLECTION.md) for Section 9C.

## Known limitations and unfinished features

- The detector uses the 15 fixed labels in [labels.json](home-inventory/config/labels.json) and a score threshold of 0.12. It can miss items or suggest an incorrect label. One kitchen drawer scan suggested scissors incorrectly. Review the list and rename, remove, or manually add items before saving. [Day 3 test results](DAY3_TEST_RESULTS.txt)
- Uploads accept JPEG and PNG up to 10 MB (10,485,760 bytes) and 4096 × 4096 pixels. The app rejects other formats and corrupt images.
- The first scan in a Flask process loads the model into memory. Later scans reuse it. The Day 3 run recorded 6.5 seconds for the first scan and 1.8 seconds for the next scan on that machine. [Day 3 test results](DAY3_TEST_RESULTS.txt)
- Search matches saved item names. Settings, Help, and location deletion are unfinished. The detector sample unit test remains skipped. The standalone sample command above exercises the real model.
- **Pending verification.** Follow these instructions on a clean machine or fresh clone with a new environment and no cached model. Then disconnect from the internet, restart Flask, and scan, correct, save, reopen, and search from the browser. The Day 4 notes list these clean setup and offline checks as planned. [Day 4 notes](DAY4_NOTES.txt)

## Technical reference

### Detector and photo scan

`model_status()` reports local model file readiness as `{"ready": bool, "detail": str}`. `scan(image_bytes)` returns `{"status": str, "items": list}` and reports model and inference failures through the status field. Each suggestion has a `name` and a numeric detector `score`. [Detector service](home-inventory/services/detector.py)

`POST /scan` accepts one image in the multipart field `photo`. Pillow checks the decoded format and dimensions and fully decodes the image. Uploads stay in memory. Flask logs elapsed scan time and returns the detector response with the following HTTP codes.

| Result | HTTP | `status` |
|---|---|---|
| Suggestions found | 200 | `ok` |
| No suggestions above the threshold | 200 | `no_detections` |
| Local model files missing | 503 | `model_unavailable` |
| Model loading or inference failed | 500 | `scan_error` |
| Upload rejected by the route | 400 | `invalid_file` |

Rejected uploads return `message`, an empty `items` list, and one of these `reason` values: `missing_file`, `file_too_large`, `unsupported_type`, or `dimensions_too_large`.

### Location and search routes

| Route | Input | Success | Errors |
|---|---|---|---|
| `POST /locations` | JSON with `label` and an array of item-name strings in `items` | 201 with `id`, `label`, `items` | 400 invalid body, 415 unsupported media type |
| `GET /locations/<id>` | Location ID | 200 with `id`, `label`, `items` | 404 unknown location |
| `POST /locations/<id>` | Same JSON as create, replacing the label and whole item list | 200 with `id`, `label`, `items` | 400, 404, 415 |
| `GET /search?q=` | Query of up to 100 characters | 200 with `query` and `results`, each containing `item`, `location_id`, `location_label` | 400 query too long |

Location and search errors return `{"error": "message"}`. Location labels must contain 1–200 characters after trimming. Each location accepts up to 200 item names of up to 100 characters each. Empty item lists and repeated location labels are allowed. Item names are trimmed, blanks are skipped, and case-insensitive duplicates keep the first spelling. Search uses a case-insensitive literal substring, including literal `%` and `_` characters. At the database layer, a blank location label raises `ValueError`, and replacing an unknown location raises `LookupError`. [Flask routes](home-inventory/app.py), [SQLite operations](home-inventory/db.py)

Saving puts the editor in update mode for that inventory. Reopening restores the saved label and items, and users can scan another photo to add suggestions. SQLite also stores location timestamps.
