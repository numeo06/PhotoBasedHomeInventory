import argparse
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.detector import load_model, scan_detections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("photos", nargs="+", type=Path)
    parser.add_argument("--threshold", type=float, default=0.10)
    args = parser.parse_args()

    for photo in args.photos:
        if not photo.is_file():
            parser.error(f"Photo not found: {photo}")

    started = perf_counter()
    load_model()
    load_seconds = perf_counter() - started
    print(f"Model load: {load_seconds:.2f}s | threshold: {args.threshold:g}")

    for index, photo in enumerate(args.photos):
        started = perf_counter()
        results = scan_detections(photo.read_bytes(), args.threshold)
        elapsed = perf_counter() - started

        if index == 0:
            print(f"Cold load + first scan: {load_seconds + elapsed:.2f}s")
        print(f"{photo.name} | scan: {elapsed:.2f}s")

        if results:
            for item in results:
                print(f"  {item['name']}: {item['score']:.3f}")
        else:
            print("  No detections above threshold")


if __name__ == "__main__":
    main()
