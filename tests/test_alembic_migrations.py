"""Static integrity checks for the Alembic revision graph."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _script_directory() -> ScriptDirectory:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_alembic_revisions_have_one_connected_head() -> None:
    """Every revision must be reachable from one head without branching."""
    script = _script_directory()
    heads = script.get_heads()

    assert len(heads) == 1, f"Expected one Alembic head, got {heads}"

    revisions = list(script.walk_revisions(base="base", head="heads"))
    revision_ids = {revision.revision for revision in revisions}
    assert revisions[-1].down_revision is None

    current = script.get_revision(heads[0])
    visited: set[str] = set()
    while current is not None:
        assert current.revision not in visited, "Alembic revision cycle detected"
        visited.add(current.revision)
        down_revision = current.down_revision
        parent_ids = (
            ()
            if down_revision is None
            else down_revision
            if isinstance(down_revision, tuple)
            else (down_revision,)
        )
        assert len(parent_ids) <= 1, (
            f"Revision {current.revision} branches from {parent_ids}; "
            "BeachOps migrations must stay linear."
        )
        current = script.get_revision(parent_ids[0]) if parent_ids else None

    assert visited == revision_ids
