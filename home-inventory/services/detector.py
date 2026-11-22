import json
import logging
from io import BytesIO
from threading import Lock
from time import perf_counter

from scripts.setup_model import MODEL_DIR, MODEL_FILES, PROJECT_ROOT

logger = logging.getLogger(__name__)
_model_lock = Lock()
_model_components = None


class ModelUnavailableError(FileNotFoundError):
    pass


def model_status():
    """Report whether the required local model files are present."""
    missing = [name for name in MODEL_FILES if not (MODEL_DIR / name).is_file()]
    if missing:
        return {"ready": False, "detail": f"Missing local model files: {', '.join(missing)}"}
    return {"ready": True, "detail": "Local OWL-ViT model files are present."}


def load_model():
    """Load and cache the local processor and CPU model."""
    global _model_components

    with _model_lock:
        if _model_components is None:
            readiness = model_status()
            if not readiness["ready"]:
                raise ModelUnavailableError(readiness["detail"])

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
    started = perf_counter()
    try:
        detections = scan_detections(image_bytes)
    except ModelUnavailableError:
        result = {"status": "model_unavailable", "items": []}
    except Exception:
        result = {"status": "scan_error", "items": []}
    else:
        result = {
            "status": "ok" if detections else "no_detections",
            "items": [
                {"name": item["name"], "score": round(item["score"], 3)}
                for item in detections
            ],
        }
    logger.info(
        "Detector scan status=%s elapsed_ms=%.1f items=%d",
        result["status"],
        (perf_counter() - started) * 1000,
        len(result["items"]),
    )
    return result
