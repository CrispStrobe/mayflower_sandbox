import os
from pathlib import PurePosixPath

import asyncpg
import pytest

from mayflower_sandbox import create_sqlite_pool, VirtualFilesystem, SandboxExecutor
from mayflower_sandbox.integrations import install_skill


@pytest.mark.asyncio
async def test_install_skill_and_import(tmp_path):
    db_path = str(tmp_path / "skills.db")
    db = await create_sqlite_pool(db_path)

    try:
        thread_id = "test_skill_thread"
        skill = await install_skill(
            db, thread_id, "github:anthropics/skills/skills/algorithmic-art"
        )

        vfs = VirtualFilesystem(db, thread_id)
        pkg_root = PurePosixPath(skill["path"])
        for relative in ("SKILL.md", "__init__.py"):
            entry = await vfs.read_file(str(pkg_root / relative))
            assert entry["content"], f"{relative} missing in VFS"

        executor = SandboxExecutor(db, thread_id)
        code = """
from skills.algorithmic_art import instructions
print(instructions()[:64])
"""
        result = await executor.execute(code)
        assert result.success
        assert "algorithmic art" in result.stdout.lower()
    finally:
        await db.close()
