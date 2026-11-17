from __future__ import annotations

import json

import pytest

from src.data_hub.artifacts import build_manifest, write_manifest


def test_manifest_contains_checksum_provenance_and_license(tmp_path):
    artifact = tmp_path / "matches.csv.gz"
    artifact.write_bytes(b"compressed-fixture")

    manifest = build_manifest(
        artifact,
        source="fixture",
        connector="test",
        license="CC BY 4.0",
        columns=["match_id", "match_date"],
        row_count=1,
        redistributable=True,
    )
    output = write_manifest(manifest, tmp_path / "manifests" / "matches.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["manifest_version"] == "1"
    assert payload["format"] == "csv.gz"
    assert payload["bytes"] == len(b"compressed-fixture")
    assert len(payload["sha256"]) == 64
    assert payload["columns"] == ["match_id", "match_date"]
    assert payload["redistributable"] is True


def test_manifest_rejects_missing_artifact(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_manifest(
            tmp_path / "missing.parquet",
            source="x",
            connector="x",
            license="unknown",
        )
