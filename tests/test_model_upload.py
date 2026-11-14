"""WS2: S3-compatible upload target for the model outputs (no network)."""
from pathlib import Path

import pytest

from twin.model.upload import UploadTarget, content_type, target_from_env


def test_no_target_without_env() -> None:
    assert target_from_env({}) is None


def test_target_reads_endpoint_bucket_and_prefix() -> None:
    env = {
        "URBS_TILES_S3_ENDPOINT": "https://acc.r2.cloudflarestorage.com",
        "URBS_TILES_BUCKET": "urbs-gemina",
        "URBS_TILES_PREFIX": "model/",
        "AWS_ACCESS_KEY_ID": "k",
        "AWS_SECRET_ACCESS_KEY": "s",
    }
    t = target_from_env(env)
    assert t == UploadTarget("https://acc.r2.cloudflarestorage.com", "urbs-gemina", "model", "k", "s", "auto")
    assert t.key_for(Path("/x/buildings.pmtiles")) == "urbs-gemina/model/buildings.pmtiles"


def test_bucket_without_endpoint_is_an_error() -> None:
    with pytest.raises(ValueError):
        target_from_env({"URBS_TILES_BUCKET": "b"})


def test_content_types() -> None:
    assert content_type(Path("a.pmtiles")) == "application/vnd.pmtiles"
    assert content_type(Path("a.json")) == "application/json"
    assert content_type(Path("a.parquet")) == "application/vnd.apache.parquet"
