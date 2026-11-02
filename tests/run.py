"""Minimal runner for environments without pytest: `python tests/run.py`. Under pytest, just run `pytest`."""

import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

failed = passed = 0
for f in sorted((ROOT / "tests").glob("test_*.py")):
    mod = importlib.import_module(f.stem)
    for name in dir(mod):
        if name.startswith("test_"):
            try:
                getattr(mod, name)()
                passed += 1
            except Exception:
                failed += 1
                print(f"FAIL {f.stem}.{name}")
                traceback.print_exc(limit=2)
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
