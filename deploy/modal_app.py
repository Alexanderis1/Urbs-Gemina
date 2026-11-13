"""Host the tool API on Modal with a stable public URL.

    pip install modal && modal setup                      # once, opens a browser to log in
    modal secret create urbs-gemina-api URBS_API_KEYS="<office-key>:office"   # add EXA_API_KEY=... when WS7 is merged
    modal run deploy/modal_app.py::fetch_layers           # download the static context layers into the volume
    modal deploy deploy/modal_app.py                      # prints https://<workspace>--urbs-gemina-tools-api.modal.run

Run from the repository root. The static layers live in the Modal volume
"urbs-gemina-layers"; Cartoradio is never stored there (read at runtime only).
"""
from __future__ import annotations

import subprocess

import modal

APP_DIR = "/root/app"
RAW_DIR = f"{APP_DIR}/data/raw"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi>=0.110", "pydantic>=2", "PyYAML>=6", "numpy>=1.26", "h3>=4", "httpx>=0.27")
    .env({"PYTHONPATH": APP_DIR, "URBS_ROOT": APP_DIR})
    .add_local_dir("twin", f"{APP_DIR}/twin", ignore=["**/__pycache__"])
    .add_local_dir("config", f"{APP_DIR}/config")
    .add_local_dir("scripts", f"{APP_DIR}/scripts", ignore=["**/__pycache__"])
    .add_local_file("data/manifest.json", f"{APP_DIR}/data/manifest.json")
)

layers = modal.Volume.from_name("urbs-gemina-layers", create_if_missing=True)
app = modal.App("urbs-gemina-tools")


@app.function(image=image, volumes={RAW_DIR: layers}, secrets=[modal.Secret.from_name("urbs-gemina-api")],
              min_containers=1, timeout=120)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def api() -> object:
    from twin.api.app import create_app

    return create_app()


@app.function(image=image, volumes={RAW_DIR: layers}, timeout=1800)
def fetch_layers() -> None:
    """Run WS1's downloader inside Modal and keep the GeoJSON files in the volume."""
    subprocess.run(["python", "scripts/fetch_static_layers.py"], cwd=APP_DIR, check=False)
    layers.commit()
