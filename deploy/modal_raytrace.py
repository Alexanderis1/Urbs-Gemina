"""Sionna RT ray tracing on a Modal GPU (scales to zero; nothing runs while idle).

    modal deploy deploy/modal_raytrace.py      # once; the app costs nothing while idle
    python scripts/raytrace_site.py --lon 12.4823 --lat 41.8960 --height 30 --band 1800 --backend modal

The client builds the 3D scene from the city model and sends it here; the GPU only
traces rays and returns path-gain maps. Settings: config/physics.yaml ``raytrace``.
"""
from __future__ import annotations

import modal

APP_DIR = "/root/app"
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("sionna-rt==2.2.0", "mapbox-earcut>=1.0", "numpy>=1.26", "scipy>=1.10", "PyYAML>=6")
    .env({"PYTHONPATH": APP_DIR, "URBS_ROOT": APP_DIR})
    .add_local_dir("twin", f"{APP_DIR}/twin", ignore=["**/__pycache__"])
    .add_local_dir("config", f"{APP_DIR}/config")
)
app = modal.App("urbs-gemina-raytrace")


# GPU, timeout and scale-to-zero match config/physics.yaml raytrace.modal (Alessandro's rule: min_containers=0).
@app.function(image=image, gpu="L4", timeout=900, min_containers=0, scaledown_window=60)
def radio_map(scene_tar: bytes, params: dict) -> bytes:  # type: ignore[type-arg]
    from twin.physics import raytrace

    return raytrace.run_scene(scene_tar, params)
