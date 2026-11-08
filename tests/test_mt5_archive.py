"""The Windows handoff tree must import only after python-dotenv is present."""

import os
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "tradingagents/__init__.py",
    "tradingagents/mt5_preflight.py",
    "tradingagents/mt5_demo.py",
    "tradingagents/mt5_model.py",
    "docs/MT5_DEMO.md",
    "docs/MT5_PREFLIGHT.md",
    "windows/Run demo dry.cmd",
    "windows/Run demo execute.cmd",
    "windows/Stop demo.cmd",
]


def _tree(tmp_path: Path) -> Path:
    folder = tmp_path / "mt5-demo-windows"
    for name in FILES:
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    (folder / "requirements.txt").write_text("python-dotenv\nnumpy\nMetaTrader5\n", encoding="utf-8")
    (folder / "README.md").write_text((ROOT / "docs" / "MT5_DEMO.md").read_text(encoding="utf-8"), encoding="utf-8")
    return folder


def test_archive_import_requires_dotenv_then_refuses_linux_orders(tmp_path: Path):
    folder = _tree(tmp_path)
    archive = tmp_path / "mt5-demo-windows.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for path in folder.rglob("*"):
            if path.is_file():
                handle.write(path, path.relative_to(folder.parent).as_posix())
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(unpacked)
    root = unpacked / "mt5-demo-windows"
    bare = subprocess.run(
        ["/usr/bin/python3", "-c", "import tradingagents.mt5_demo"],
        cwd=root,
        env={"PYTHONPATH": str(root), "PATH": "/usr/bin", "PYTHONNOUSERSITE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert bare.returncode != 0
    site = Path("/workspace/.venv/lib/python3.12/site-packages")
    ran = subprocess.run(
        ["/usr/bin/python3", "-m", "tradingagents.mt5_demo", "--execute-demo"],
        cwd=root,
        env={"PYTHONPATH": f"{root}{os.pathsep}{site}", "PATH": "/usr/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 2
    assert "No terminal was opened" in ran.stderr
    assert "555001" not in ran.stderr
