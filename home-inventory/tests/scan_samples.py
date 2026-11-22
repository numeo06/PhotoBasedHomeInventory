import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from services.detector import scan


def main():
    for filename in ("drawer1.jpg", "drawer2.jpg"):
        photo = PROJECT_ROOT / "samples" / filename
        print(filename)
        print(json.dumps(scan(photo.read_bytes())))


if __name__ == "__main__":
    main()
