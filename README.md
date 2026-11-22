# PhotoBasedHomeInventory
Local web app that answers “where did I put that?”: upload a drawer photo, review AI-suggested items from an on-device OWL-ViT model, save them to SQLite, and search by keyword. No API key needed.

## Local setup on Windows

Run the standalone OWL-ViT detector from the project root in PowerShell.

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

If the legacy `py` launcher does not see the Python Install Manager's copy of 3.11, use `pymanager exec -V:3.11 -m venv .venv` for the first line. The version check should print Python 3.11.x. The commands below use the virtual environment's Python directly.

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
.\.venv\Scripts\python.exe .\scripts\setup_model.py
```

The script creates `models/owlvit-base-patch32/` and downloads the pinned public snapshot, including about 613 MB of weights. Wait for `Model ready:` and the revision output. Git ignores both `.venv/` and `models/`, so each checkout creates them locally.

### 5. Run the sample scan

```powershell
.\.venv\Scripts\python.exe .\scripts\test_owlvit.py .\samples\drawer1.jpg .\samples\drawer1.jpg .\samples\drawer2.jpg --threshold 0.12
```

The script prints model load time, cold load plus first scan, per-photo elapsed times, and item suggestions with detector scores. The repeated first image measures a warm run on the same input. You can change the score filter with `--threshold`. This check runs independently of Flask.
