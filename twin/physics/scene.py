"""Export LoD1 city-model buildings as a Sionna RT / Mitsuba scene (binary PLY meshes + XML).

Walls are vertical quads on every ring edge (outer walls and courtyard walls),
roofs are flat polygons triangulated with holes (earcut), and a square ground
plane closes the scene. Coordinates are local metres: x east, y north, z up,
origin at ``Buildings.lon0, lat0``. Materials are ITU-R P.2040 / P.527 types
from config/physics.yaml ``raytrace``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from twin.physics import config
from twin.physics.buildings import Buildings

F64 = NDArray[np.float64]
I64 = NDArray[np.int64]


def _signed_area(ring: F64) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _open(ring: F64) -> F64:
    return ring[:-1] if ring.shape[0] > 1 and np.allclose(ring[0], ring[-1]) else ring


def _polygons(rings: list[tuple[F64, bool]]) -> list[list[F64]]:
    """Group rings as [outer, hole, hole, ...]; outer made counter-clockwise, holes clockwise."""
    groups: list[list[F64]] = []
    for ring, is_outer in rings:
        r = _open(ring)
        if r.shape[0] < 3 or abs(_signed_area(r)) < 1e-6:
            continue
        ccw = _signed_area(r) > 0
        if is_outer or not groups:
            groups.append([r if ccw else r[::-1]])
        else:
            groups[-1].append(r[::-1] if ccw else r)
    return groups


def extrude(city: Buildings, heights: F64 | None = None) -> tuple[F64, I64]:
    """Vertices (V, 3) and triangles (F, 3) of all buildings."""
    import mapbox_earcut as earcut

    h_all = city.heights if heights is None else heights
    verts: list[F64] = []
    faces: list[I64] = []
    base = 0
    for b, rings in enumerate(city.rings):
        h = float(h_all[b])
        if h <= 0.0:
            continue
        for poly in _polygons(rings):
            for ring in poly:
                n = ring.shape[0]
                bottom = np.column_stack([ring, np.zeros(n)])
                top = np.column_stack([ring, np.full(n, h)])
                verts.extend([bottom, top])
                i = np.arange(n)
                j = (i + 1) % n
                faces.append(np.column_stack([base + i, base + j, base + n + j]))
                faces.append(np.column_stack([base + i, base + n + j, base + n + i]))
                base += 2 * n
            flat = np.concatenate(poly)
            ends = np.cumsum([r.shape[0] for r in poly]).astype(np.uint32)
            tri = np.asarray(earcut.triangulate_float64(flat, ends), dtype=np.int64).reshape(-1, 3)
            if tri.size:
                a, bb, c = flat[tri[:, 0]], flat[tri[:, 1]], flat[tri[:, 2]]
                up = (bb[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (bb[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
                tri = np.where((up < 0)[:, None], tri[:, ::-1], tri)
                verts.append(np.column_stack([flat, np.full(flat.shape[0], h)]))
                faces.append(base + tri)
                base += flat.shape[0]
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.concatenate(verts), np.concatenate(faces).astype(np.int64)


def write_ply(path: Path, verts: F64, faces: I64) -> None:
    header = (f"ply\nformat binary_little_endian 1.0\nelement vertex {len(verts)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              f"element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n").encode()
    v = np.asarray(verts, dtype="<f4").tobytes()
    rec = np.zeros(len(faces), dtype=[("n", "u1"), ("i", "<i4", (3,))])
    rec["n"] = 3
    rec["i"] = faces
    path.write_bytes(header + v + rec.tobytes())


def _ground(half: float) -> tuple[F64, I64]:
    v = np.array([[-half, -half, 0.0], [half, -half, 0.0], [half, half, 0.0], [-half, half, 0.0]])
    return v, np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)



def write_scene(city: Buildings, out_dir: Path, ground_half_m: float, heights: F64 | None = None) -> Path:
    """Write meshes/buildings.ply, meshes/ground.ply and scene.xml; return the XML path."""
    wall = str(config.value("raytrace", "wall_material"))
    thick = float(config.value("raytrace", "wall_thickness_m"))
    ground = str(config.value("raytrace", "ground_material"))
    meshes = out_dir / "meshes"
    meshes.mkdir(parents=True, exist_ok=True)
    verts, faces = extrude(city, heights)
    write_ply(meshes / "buildings.ply", verts, faces)
    gv, gf = _ground(ground_half_m)
    write_ply(meshes / "ground.ply", gv, gf)
    xml = f"""<scene version="2.1.0">
    <bsdf type="itu-radio-material" id="mat-wall_material">
        <string name="type" value="{wall}"/>
        <float name="thickness" value="{thick}"/>
    </bsdf>
    <bsdf type="itu-radio-material" id="mat-ground_material">
        <string name="type" value="{ground}"/>
        <float name="thickness" value="1.0"/>
    </bsdf>
    <shape type="ply" id="mesh-buildings">
        <string name="filename" value="meshes/buildings.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-wall_material" name="bsdf"/>
    </shape>
    <shape type="ply" id="mesh-ground">
        <string name="filename" value="meshes/ground.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-ground_material" name="bsdf"/>
    </shape>
</scene>
"""
    path = out_dir / "scene.xml"
    path.write_text(xml, encoding="utf-8")
    return path
