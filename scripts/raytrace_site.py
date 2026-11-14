"""Ray-trace one antenna site with Sionna RT and cache the radio maps for the field API.

  python scripts/raytrace_site.py --lon 12.4823 --lat 41.8960 --height 30 --band 1800 --backend modal
  python scripts/raytrace_site.py ... --backend local --samples 200000    # CPU (LLVM), small test

Backends: ``modal`` calls the deployed app ``urbs-gemina-raytrace`` (deploy/modal_raytrace.py,
GPU, scales to zero); ``local`` needs ``pip install sionna-rt`` in this environment.
The maps go to data/cache/raytrace/ and /mnt/project-files/raytrace/ (key = site + settings).
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Any

from twin.physics import config, raytrace


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--height", type=float, required=True, help="antenna centre above ground, m")
    p.add_argument("--band", default=None)
    p.add_argument("--sectors", default=None, help='JSON list, e.g. [{"azimuth_deg": 0}, {"azimuth_deg": 120}]')
    p.add_argument("--radius", type=float, default=300.0)
    p.add_argument("--backend", choices=["modal", "local"], default="modal")
    p.add_argument("--samples", type=int, default=None, help="override samples_per_tx (tests; not cached)")
    args = p.parse_args()
    site: dict[str, Any] = {"lon": args.lon, "lat": args.lat, "height_m": args.height, "band": args.band}
    if args.sectors:
        site["sectors"] = json.loads(args.sectors)
    t0 = time.time()
    scene, params = raytrace.prepare(site, args.radius, config.frequency_mhz(args.band))
    if args.samples:
        params["samples_per_tx"] = args.samples
    print(f"scene: {params['meta']['buildings']} buildings, {len(scene) / 1e6:.1f} MB, "
          f"{len(params['transmitters'])} transmitters")
    if args.backend == "local":
        blob = raytrace.run_scene(scene, params)
    else:
        import modal  # type: ignore[import-not-found,unused-ignore]

        fn = modal.Function.from_name("urbs-gemina-raytrace", "radio_map")
        blob = fn.remote(scene, params)
    maps = raytrace.RadioMaps.from_bytes(blob)
    paths = [] if args.samples else raytrace.save_cached(site, maps, args.radius)
    print(json.dumps({"key": raytrace.site_key(site, args.radius), "shape": list(maps.path_gain.shape),
                      "seconds": round(time.time() - t0, 1), "saved": [str(x) for x in paths]}, indent=2))


if __name__ == "__main__":
    main()
