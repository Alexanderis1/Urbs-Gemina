"""Host the tool API on Modal with a stable public URL.

    pip install modal && modal setup                      # once, opens a browser to log in
    modal secret create urbs-gemina-api URBS_API_KEYS="<office-key>:office" \
        ANTHROPIC_API_KEY=... EXA_API_KEY=... VOICE_SECRET_OFFICE=... VOICE_SECRET_CITIZEN=...
    modal run deploy/modal_app.py::fetch_layers           # download the static context layers into the volume
    modal deploy deploy/modal_app.py                      # prints https://<workspace>--urbs-gemina-tools-api.modal.run

Run from the repository root. The static layers live in the Modal volume
"urbs-gemina-layers"; Cartoradio is never stored there (read at runtime only).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import modal

APP_DIR = "/root/app"
RAW_DIR = f"{APP_DIR}/data/raw"
PROCESSED_DIR = f"{APP_DIR}/data/processed"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi>=0.110", "pydantic>=2", "PyYAML>=6", "numpy>=1.26", "h3>=4", "httpx>=0.27", "anthropic>=2.8",
                 # WS3 live providers (Cartoradio GeoTIFF, register fit, GTFS-RT, EEA parquet)
                 "rasterio>=1.3", "scipy>=1.10", "pyarrow>=14", "gtfs-realtime-bindings>=1.0", "protobuf>=4")
    .env({"PYTHONPATH": APP_DIR, "URBS_ROOT": APP_DIR})
    .add_local_dir("twin", f"{APP_DIR}/twin", ignore=["**/__pycache__"])
    .add_local_dir("config", f"{APP_DIR}/config")
    .add_local_dir("scripts", f"{APP_DIR}/scripts", ignore=["**/__pycache__"])
    .add_local_file("data/manifest.json", f"{APP_DIR}/data/manifest.json")
)
for optional in ("agents", "voice"):  # WS7 orchestrator and WS9 voice webhook, once merged
    if Path(optional).is_dir():
        image = image.add_local_dir(optional, f"{APP_DIR}/{optional}", ignore=["**/__pycache__"])
SEED_DIR = f"{APP_DIR}/seed"
if Path("data/raw/sports_web").is_dir():  # WS10 agent outputs, copied into the volume by fetch_layers
    image = image.add_local_dir("data/raw/sports_web", f"{SEED_DIR}/sports_web")

layers = modal.Volume.from_name("urbs-gemina-layers", create_if_missing=True)
processed = modal.Volume.from_name("urbs-gemina-processed", create_if_missing=True)
VOLUMES = {RAW_DIR: layers, PROCESSED_DIR: processed}
app = modal.App("urbs-gemina-tools")


@app.function(image=image, volumes=VOLUMES, secrets=[modal.Secret.from_name("urbs-gemina-api")],
              min_containers=0, scaledown_window=300, timeout=300)  # sleeps when idle to save credits
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def api() -> object:
    from twin.api.app import create_app

    return create_app()


@app.function(image=image, volumes=VOLUMES, timeout=1800)
def fetch_layers() -> None:
    """Run WS1's downloader inside Modal and keep the GeoJSON files in the volume; then build the sports layer."""
    subprocess.run(["python", "scripts/fetch_static_layers.py"], cwd=APP_DIR, check=False)
    if Path(f"{SEED_DIR}/sports_web").is_dir():
        shutil.copytree(f"{SEED_DIR}/sports_web", f"{RAW_DIR}/sports_web", dirs_exist_ok=True)
    layers.commit()
    subprocess.run(["python", "-m", "twin.modules.sports.pipeline", "build"], cwd=APP_DIR, check=False)
    layers.commit()  # keeps the sports geocode cache
    processed.commit()
