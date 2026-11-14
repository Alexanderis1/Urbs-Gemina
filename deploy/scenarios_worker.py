"""Modal worker for the heavy scenario kinds (WS6): SUMO traffic, floods, plumes.

    modal deploy deploy/scenarios_worker.py

Scales to zero (min_containers=0). The tool API sends isolated kinds here when
URBS_SCENARIO_WORKER=modal is set in its environment. SUMO runs as a subprocess
inside this container; the eclipse-sumo package is never imported, because its
import points PROJ at SUMO's own database and breaks rasterio.
Layers come from the same volumes as the tool API; road networks built from
OpenStreetMap are cached in their own volume.
"""
from __future__ import annotations

from typing import Any

import modal

APP_DIR = "/root/app"
image = (
    modal.Image.debian_slim(python_version="3.12")
    # eclipse-sumo's binaries (sumo, duarouter) link X11 and GL even without a GUI; without these
    # duarouter dies silently and randomTrips --validate finds no routes.rou.xml.
    .apt_install("libx11-6", "libxext6", "libxrender1", "libgl1", "libatomic1")
    .pip_install("PyYAML>=6", "numpy>=1.26", "scipy>=1.10", "rasterio>=1.3", "eclipse-sumo>=1.20",
                 "httpx>=0.27", "pyarrow>=14", "gtfs-realtime-bindings>=1.0", "protobuf>=4")
    .env({"PYTHONPATH": APP_DIR, "URBS_ROOT": APP_DIR})
    .add_local_dir("twin", f"{APP_DIR}/twin", ignore=["**/__pycache__"])
    .add_local_dir("config", f"{APP_DIR}/config")
)
VOLUMES = {
    f"{APP_DIR}/data/raw": modal.Volume.from_name("urbs-gemina-layers", create_if_missing=True),
    f"{APP_DIR}/data/processed": modal.Volume.from_name("urbs-gemina-processed", create_if_missing=True),
    f"{APP_DIR}/data/cache": modal.Volume.from_name("urbs-gemina-scenario-cache", create_if_missing=True),
}
app = modal.App("urbs-gemina-scenarios")


@app.function(image=image, volumes=VOLUMES, cpu=4.0, memory=8192, timeout=1800,
              min_containers=0, scaledown_window=120)
def run_heavy(kind: str, area: Any, change: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    from twin.scenarios import engine, remote

    out = engine.run(kind, area, change, data=remote.from_spec(spec), isolate=False)
    VOLUMES[f"{APP_DIR}/data/cache"].commit()
    return out
