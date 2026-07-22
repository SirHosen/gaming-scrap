"""Tests for CSV / JSON export."""
import json
import tempfile
from pathlib import Path

from nestfetch import exporters
from nestfetch.models import Game, Mirror


def _sample():
    return Game(
        title="Alpha Quest",
        meta_size="1.2 GB",
        meta_genre="RPG",
        detail_url="https://x/alpha",
        source_site="switchroms",
        category="switch-rom",
        platform="Nintendo Switch",
        mirrors=[Mirror(format="NSP ROM", size="1.2 GB", hoster="Mediafire",
                        redirect_url="https://x/alpha/r", final_link="https://mediafire.com/f")],
    )


def test_export_both_formats():
    orig = exporters.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as d:
        exporters.OUTPUT_DIR = d
        try:
            paths = exporters.export_data([_sample()], "both")
        finally:
            exporters.OUTPUT_DIR = orig

        assert len(paths) == 2
        csv_path = next(p for p in paths if str(p).endswith(".csv"))
        json_path = next(p for p in paths if str(p).endswith(".json"))

        assert Path(csv_path).parent.name == "switchroms"
        assert Path(csv_path).name == "switchroms.csv"
        assert Path(json_path).parent.name == "switchroms"
        assert Path(json_path).name == "switchroms.json"

        csv_text = Path(csv_path).read_text(encoding="utf-8-sig")
        assert "Game Title" in csv_text          # header present
        assert "Alpha Quest" in csv_text
        assert "Mediafire" in csv_text

        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["title"] == "Alpha Quest"
        assert data[0]["mirrors"][0]["hoster"] == "Mediafire"


def test_export_custom_site_and_folder_creation():
    orig = exporters.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as d:
        exporters.OUTPUT_DIR = d
        try:
            paths = exporters.export_data([_sample()], "both", site_name="nxbrew")
        finally:
            exporters.OUTPUT_DIR = orig

        assert len(paths) == 2
        csv_path = next(p for p in paths if str(p).endswith(".csv"))
        json_path = next(p for p in paths if str(p).endswith(".json"))

        assert Path(csv_path).parent.name == "nxbrew"
        assert Path(csv_path).name == "nxbrew.csv"
        assert Path(json_path).parent.name == "nxbrew"
        assert Path(json_path).name == "nxbrew.json"
        assert Path(csv_path).exists()
        assert Path(json_path).exists()


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
