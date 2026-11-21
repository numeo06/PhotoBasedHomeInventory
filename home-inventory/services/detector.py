"""Local OWL-ViT detector (owner: Person B).

TEMPORARY STUB: returns fake data so Person A can build the page.
Person B replaces the function BODIES, not the signatures or the returned shape.

Agreed interface:
    model_status() -> {"ready": bool, "detail": str}
    scan(image_bytes: bytes) -> {
        "status": "ok" | "no_detections" | "model_unavailable" | "scan_error",
        "items": [{"name": str, "score": float}],
    }
scan() must never raise to the caller.
"""


def model_status() -> dict:
    """STUB: the real version checks the model folder without loading it."""
    return {"ready": False, "detail": "stub: real model not wired yet"}


def scan(image_bytes: bytes) -> dict:
    """STUB: ignores the image and returns fixed fake suggestions."""
    return {
        "status": "ok",
        "items": [
            {"name": "scissors", "score": 0.26},
            {"name": "tape measure", "score": 0.31},
        ],
    }
