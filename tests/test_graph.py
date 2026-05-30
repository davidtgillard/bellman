"""Graph sync tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyfits.result import Ok

from snark.graph.link_naming import display_name, precedes_link_type
from snark.graph.sync import init_pyfits_repo, libfits_available, sync_roadmap
from snark.model import Hardness, RelationType

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "roadmap"


def test_link_naming() -> None:
    lt = precedes_link_type(RelationType.FS, Hardness.MANDATORY)
    assert lt == "precedes_FS_Mandatory"
    assert display_name(lt, "a", "b") == "precedes_FS_Mandatory:a->b"


@pytest.mark.integration
def test_sync_example_roadmap(tmp_path: Path) -> None:
    if not libfits_available():
        pytest.skip("libfits not available")
    import shutil

    shutil.copytree(EXAMPLES, tmp_path / "roadmap")
    root = tmp_path / "roadmap"
    init_result = init_pyfits_repo(root)
    assert isinstance(init_result, Ok)
    result = sync_roadmap(root)
    assert isinstance(result, Ok)
    repeat = sync_roadmap(root)
    assert isinstance(repeat, Ok)
