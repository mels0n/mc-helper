import subprocess
import sys
from pathlib import Path


def test_generated_reference_is_current() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "gen_reference.py"
    result = subprocess.run([sys.executable, str(script), "--check"], check=False)
    assert result.returncode == 0, "run: python scripts/gen_reference.py --write"
