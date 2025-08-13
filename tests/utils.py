import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_json(temp_dir: Path, filename: str):
    """Load a JSON file from the temp directory."""
    path = temp_dir / filename
    return json.loads(path.read_text(encoding="utf-8"))


def run_main_in_dir(temp_dir: Path):
    """Run main.py inside the given temporary directory."""
    # Copy all required files to temp_dir
    for filename in ["main.py"]:
        shutil.copy(filename, temp_dir / filename)

    # Execute main.py with working directory as temp_dir
    subprocess.run(
        ["python", "main.py"],
        cwd=temp_dir,
        check=True
    )


def make_temp_dir():
    """Create a temporary directory for test isolation."""
    return Path(tempfile.mkdtemp())
