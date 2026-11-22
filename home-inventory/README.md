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
