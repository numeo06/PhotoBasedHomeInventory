import json
from io import BytesIO
from threading import Lock

from scripts.setup_model import MODEL_DIR, MODEL_FILES, PROJECT_ROOT

_model_lock = Lock()
_model_components = None


class ModelUnavailableError(FileNotFoundError):
    pass


def load_model():
    """Load and cache the local processor and CPU model."""
    global _model_components

    with _model_lock:
        if _model_components is None:
            missing = [name for name in MODEL_FILES if not (MODEL_DIR / name).is_file()]
            if missing:
                raise ModelUnavailableError(f"Missing local model files: {', '.join(missing)}")

            from transformers import OwlViTForObjectDetection, OwlViTProcessor

            processor = OwlViTProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
            model = OwlViTForObjectDetection.from_pretrained(
                MODEL_DIR, local_files_only=True, use_safetensors=True
            ).to("cpu").eval()
            _model_components = processor, model

        return _model_components


def scan_detections(image_bytes, threshold=None):
    """Return scored detections with pixel boxes in [x1, y1, x2, y2] order."""
    processor, model = load_model()

    import torch
    from PIL import Image, ImageOps

    config = json.loads((PROJECT_ROOT / "config" / "labels.json").read_text(encoding="utf-8"))
    queries = [config["labels"]]
    if threshold is None:
        threshold = config["threshold"]

    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    inputs = processor(images=image, text=queries, return_tensors="pt")
    with torch.inference_mode():
        predictions = model(**inputs)

    detections = processor.post_process_grounded_object_detection(
        predictions,
        target_sizes=torch.tensor([[image.height, image.width]]),
        threshold=threshold,
        text_labels=queries,
    )[0]

    best = {}
    for label, score, box in zip(
        detections["text_labels"], detections["scores"].tolist(), detections["boxes"].tolist()
    ):
        name = label.strip().casefold()
        if name not in best or score > best[name]["score"]:
            best[name] = {"name": name, "score": score, "box": box}

    return sorted(best.values(), key=lambda item: item["score"], reverse=True)


def scan(image_bytes):
    """Scan encoded photo bytes and return a JSON-serializable result."""
    try:
        detections = scan_detections(image_bytes)
    except ModelUnavailableError:
        return {"status": "model_unavailable", "items": []}
    except Exception:
        return {"status": "scan_error", "items": []}

    if not detections:
        return {"status": "no_detections", "items": []}

    return {
        "status": "ok",
        "items": [
            {"name": item["name"], "score": round(item["score"], 3)}
            for item in detections
        ],
    }
