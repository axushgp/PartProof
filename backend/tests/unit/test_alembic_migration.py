import os
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_single_head_and_migration_chain():
    """
    Priority 1 & Testing Gate: Proves that Alembic migrations have a single head
    and a consistent, unbroken chain up to d4f2a1b9e8c3.
    """
    ini_path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
    assert os.path.exists(ini_path), f"alembic.ini not found at {ini_path}"

    config = Config(ini_path)
    script = ScriptDirectory.from_config(config)

    # 1. Single head
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 head, got {heads}"
    assert heads[0] == "d4f2a1b9e8c3"

    # 2. Inspect head revision
    head_rev = script.get_revision("d4f2a1b9e8c3")
    assert head_rev is not None
    assert head_rev.down_revision == "c7b1e8432a10"

    # 3. Traverse down to base to ensure no orphans
    curr = head_rev
    visited = []
    while curr is not None:
        visited.append(curr.revision)
        if curr.down_revision:
            curr = script.get_revision(curr.down_revision)
        else:
            break

    assert "d4f2a1b9e8c3" in visited
    assert "c7b1e8432a10" in visited
    assert "91eed4defee2" in visited
    assert "f6ca88a5db34" in visited
