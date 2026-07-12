"""Artifact path safety for Cursor downloads."""

from __future__ import annotations

from beachops.services.run_artifacts import _safe_artifact_path


def test_safe_artifact_path_rejects_traversal() -> None:
    assert _safe_artifact_path("../etc/passwd") is None
    assert _safe_artifact_path("artifacts/../../secret") is None


def test_safe_artifact_path_normalizes_and_allows_images() -> None:
    assert _safe_artifact_path("artifacts/shot.png") == "artifacts/shot.png"
    assert _safe_artifact_path("opt/cursor/artifacts/demo.jpg") == "artifacts/demo.jpg"
    assert _safe_artifact_path("report.exe") is None
