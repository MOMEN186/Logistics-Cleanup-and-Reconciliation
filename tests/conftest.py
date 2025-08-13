import pytest
from pathlib import Path


@pytest.fixture
def temp_dir(tmp_path: Path):
    # Simple alias so both test files can use the same fixture name
    return tmp_path
