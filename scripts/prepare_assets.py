"""Copy MediaPipe WASM and fetch the official pose model for offline runtime use.

Run from any working directory with Python 3.10 or newer. Downloads occur during
setup only; workout video never passes through this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
MODEL_FILENAME = "pose_landmarker_lite.task"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_assets(project_root: Path, force_download: bool = False,
                   skip_download: bool = False) -> dict:
    package_root = project_root / "frontend/node_modules/@mediapipe/tasks-vision"
    source_wasm = package_root / "wasm"
    if not source_wasm.is_dir() or not any(source_wasm.glob("*.wasm")):
        raise FileNotFoundError(
            f"MediaPipe WASM files are missing at {source_wasm}. "
            "Install the frontend dependencies with pnpm install first."
        )

    public_root = project_root / "frontend/public"
    destination_wasm = public_root / "wasm"
    shutil.copytree(source_wasm, destination_wasm, dirs_exist_ok=True)
    model_root = public_root / "models"
    model_root.mkdir(parents=True, exist_ok=True)
    model_path = model_root / MODEL_FILENAME

    needs_download = force_download or not model_path.is_file()
    if model_path.is_file() and model_path.stat().st_size < 1024 * 1024:
        needs_download = True
    if needs_download:
        if skip_download:
            raise FileNotFoundError(
                f"A complete pose model is missing at {model_path}. "
                "Run again without --skip-download when online."
            )
        print("Downloading the official MediaPipe Pose Landmarker Lite model...", flush=True)
        # Stage the download next to its destination so replacement is atomic.
        # A failed or interrupted transfer never overwrites a working model.
        download_path: Path | None = None
        try:
            request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "Repwise-Setup/0.1"})
            with urllib.request.urlopen(request, timeout=90) as response:
                expected_size = response.headers.get("Content-Length")
                with tempfile.NamedTemporaryFile(
                    prefix="pose-", suffix=".part", dir=model_root, delete=False
                ) as destination:
                    download_path = Path(destination.name)
                    shutil.copyfileobj(response, destination)
            actual_size = download_path.stat().st_size
            if actual_size < 1024 * 1024:
                raise ValueError("Downloaded model is unexpectedly small; refusing to use it.")
            if expected_size is not None and actual_size != int(expected_size):
                raise ValueError("Model download is incomplete; run setup again.")
            download_path.replace(model_path)
        finally:
            if download_path is not None and download_path.exists():
                download_path.unlink()

    package_info = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    wasm_files = sorted(path for path in source_wasm.rglob("*") if path.is_file())
    manifest = {
        "mediapipe_version": package_info["version"],
        "model_source": MODEL_URL,
        "model_file": MODEL_FILENAME,
        "model_bytes": model_path.stat().st_size,
        "model_sha256": sha256(model_path),
        "wasm_files": [str(path.relative_to(source_wasm)).replace("\\", "/") for path in wasm_files],
    }
    (model_root / "assets-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Copied {len(wasm_files)} MediaPipe runtime files.", flush=True)
    print(f"Model ready: {model_path} ({manifest['model_bytes']:,} bytes)", flush=True)
    print(f"SHA-256: {manifest['model_sha256']}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    download_group = parser.add_mutually_exclusive_group()
    download_group.add_argument("--force-download", action="store_true")
    download_group.add_argument("--skip-download", action="store_true")
    arguments = parser.parse_args()
    try:
        prepare_assets(arguments.project_root.resolve(), arguments.force_download,
                       arguments.skip_download)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Asset preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
