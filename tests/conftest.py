"""Shared test fixtures."""
import asyncio
import inspect
import os
import pytest
from pathlib import Path

# Force mock mode for all tests
os.environ["AURA_JEV_MOCK_MODE"] = "true"
os.environ["AURA_DATA_DIR"] = "./data/test"
os.environ["GOOGLE_API_KEY"] = "test-key-placeholder"


def pytest_pyfunc_call(pyfuncitem):
    """Enable native asyncio execution for async test functions without external plugin."""
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        funcargs = {arg: pyfuncitem.funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        asyncio.run(pyfuncitem.obj(**funcargs))
        return True


@pytest.fixture
def config():
    from aura.config import AURAConfig
    return AURAConfig.from_env()


@pytest.fixture
def workspace_root(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass\n")
    return tmp_path
