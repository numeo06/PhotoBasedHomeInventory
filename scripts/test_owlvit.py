import argparse
from pathlib import Path
from time import perf_counter

import torch
from PIL import Image, ImageOps
from transformers import OwlViTForObjectDetection, OwlViTProcessor

from setup_model import MODEL_DIR

LABELS = [
    "scissors", "screwdriver", "pliers", "tape measure",
    "flashlight", "marker", "stapler",
    "laundry detergent jug", "dishwasher detergent container",
    "box of borax", "spray bottle", "hammer",
    "wrench", "roll of masking tape", "wire stripper",
]


def scan(photo, processor, model, threshold):
    with Image.open(photo) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    queries = [LABELS]
    inputs = processor(images=image, text=queries, return_tensors="pt")

    with torch.inference_mode():
        predictions = model(**inputs)

    detections = processor.post_process_grounded_object_detection(
        predictions,
        target_sizes=torch.tensor([[image.height, image.width]]),
        threshold=threshold,
        text_labels=queries,
    )[0]

    best_scores = {}
    for label, score in zip(detections["text_labels"], detections["scores"].tolist()):
        best_scores[label] = max(best_scores.get(label, 0.0), score)

    return sorted(best_scores.items(), key=lambda item: item[1], reverse=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("photos", nargs="+", type=Path)
    parser.add_argument("--threshold", type=float, default=0.10)
    args = parser.parse_args()

    for photo in args.photos:
        if not photo.is_file():
            parser.error(f"Photo not found: {photo}")

    started = perf_counter()
    processor = OwlViTProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
    model = OwlViTForObjectDetection.from_pretrained(
        MODEL_DIR, local_files_only=True, use_safetensors=True
    ).eval()
    load_seconds = perf_counter() - started
    print(f"Model load: {load_seconds:.2f}s | threshold: {args.threshold:g}")

    for index, photo in enumerate(args.photos):
        started = perf_counter()
        results = scan(photo, processor, model, args.threshold)
        elapsed = perf_counter() - started

        if index == 0:
            print(f"Cold load + first scan: {load_seconds + elapsed:.2f}s")
        print(f"{photo.name} | scan: {elapsed:.2f}s")

        if results:
            for label, score in results:
                print(f"  {label}: {score:.3f}")
        else:
            print("  No detections above threshold")


if __name__ == "__main__":
    main()