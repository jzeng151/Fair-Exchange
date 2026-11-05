"""Path bootstrap so `pytest ../eval/tests` (CI) resolves `fx_evals`: the eval package is
not a project dependency, it is the repo's own source under `eval/src`."""
import sys
from pathlib import Path

EVAL_SRC = Path(__file__).resolve().parents[1] / "src"
if str(EVAL_SRC) not in sys.path:
    sys.path.insert(0, str(EVAL_SRC))