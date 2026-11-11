"""Load pure modules without importing Calibre or replacing installed modules."""
import sys
import types
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
if "webnovel_metadata" not in sys.modules:
    package = types.ModuleType("webnovel_metadata")
    package.__path__ = [str(SOURCE)]
    sys.modules["webnovel_metadata"] = package
