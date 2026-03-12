import sys
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import _pytest.pathlib as _pytest_pathlib
    import _pytest.tmpdir as _pytest_tmpdir

    def _patched_getbasetemp(self):  # type: ignore[no-untyped-def]
        if getattr(self, "_basetemp", None) is not None:
            return self._basetemp
        temp_root = ROOT / "tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self._basetemp = Path(
            tempfile.mkdtemp(prefix="coala-pytest-", dir=str(temp_root))
        ).resolve()
        return self._basetemp

    def _noop_cleanup_dead_symlinks(root: Path) -> None:
        return None

    _pytest_tmpdir.TempPathFactory.getbasetemp = _patched_getbasetemp
    _pytest_pathlib.cleanup_dead_symlinks = _noop_cleanup_dead_symlinks
    _pytest_tmpdir.cleanup_dead_symlinks = _noop_cleanup_dead_symlinks
except Exception:
    pass


@pytest.fixture
def tmp_path():
    root = ROOT / "tests_runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"coala-case-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)
