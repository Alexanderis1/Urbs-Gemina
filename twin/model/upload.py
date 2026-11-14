"""Upload model outputs to any S3-compatible store (Cloudflare R2, AWS S3, MinIO...).

Configured only through environment variables, so no endpoint or key lives in the repo:
URBS_TILES_S3_ENDPOINT, URBS_TILES_BUCKET, optional URBS_TILES_PREFIX and URBS_TILES_REGION,
and the usual AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
The viewer reads PMTiles with HTTP range requests: the bucket must allow public GET and CORS for Range.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

CONTENT_TYPES = {
    ".pmtiles": "application/vnd.pmtiles",
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
    ".parquet": "application/vnd.apache.parquet",
}


@dataclass(frozen=True)
class UploadTarget:
    endpoint: str
    bucket: str
    prefix: str
    access_key: Optional[str]
    secret_key: Optional[str]
    region: str

    def key_for(self, path: Path) -> str:
        parts = [self.bucket] + ([self.prefix] if self.prefix else []) + [path.name]
        return "/".join(parts)


def target_from_env(env: Mapping[str, str]) -> Optional[UploadTarget]:
    bucket = env.get("URBS_TILES_BUCKET")
    if not bucket:
        return None
    endpoint = env.get("URBS_TILES_S3_ENDPOINT")
    if not endpoint:
        raise ValueError("URBS_TILES_BUCKET is set but URBS_TILES_S3_ENDPOINT is not")
    return UploadTarget(
        endpoint=endpoint.rstrip("/"),
        bucket=bucket,
        prefix=env.get("URBS_TILES_PREFIX", "").strip("/"),
        access_key=env.get("AWS_ACCESS_KEY_ID"),
        secret_key=env.get("AWS_SECRET_ACCESS_KEY"),
        region=env.get("URBS_TILES_REGION", "auto"),
    )


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix, "application/octet-stream")


def upload(paths: list[Path], target: UploadTarget) -> list[str]:
    """Copy each file to the bucket; returns the object keys written."""
    import pyarrow.fs as pafs

    scheme, _, host = target.endpoint.partition("://")
    fs = pafs.S3FileSystem(
        access_key=target.access_key, secret_key=target.secret_key, region=target.region,
        endpoint_override=host or scheme, scheme=scheme if host else "https",
    )
    keys = []
    for p in paths:
        key = target.key_for(p)
        with open(p, "rb") as src, fs.open_output_stream(key, metadata={"Content-Type": content_type(p)}) as dst:
            for chunk in iter(lambda: src.read(8 << 20), b""):
                dst.write(chunk)
        keys.append(key)
    return keys
