from pathlib import Path

from huggingface_hub import snapshot_download

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models" / "owlvit-base-patch32"
MODEL_ID = "google/owlvit-base-patch32"
REVISION = "cbc355fb364588351c5d51c7f74465e8e7ec6f72"

MODEL_FILES = [
    "config.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.json",
    "merges.txt",
    "model.safetensors",
]


def main():
    snapshot_download(
        repo_id=MODEL_ID,
        revision=REVISION,
        local_dir=MODEL_DIR,
        allow_patterns=MODEL_FILES,
        token=False,
    )

    missing = [name for name in MODEL_FILES if not (MODEL_DIR / name).is_file()]
    if missing:
        raise SystemExit(f"Setup incomplete. Missing: {', '.join(missing)}")

    print(f"Model ready: {MODEL_DIR}")
    print(f"Revision: {REVISION}")


if __name__ == "__main__":
    main()