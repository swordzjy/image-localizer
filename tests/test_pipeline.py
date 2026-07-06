from pathlib import Path

from image_localizer.models import ImageAsset, TextBlock
from image_localizer.pipeline import _write_texts


def test_write_texts_emits_source_and_target_pairs(tmp_path):
    # Two blocks on the same visual line share one translation; the export must
    # pair the joined source text with its target translation.
    blocks = [
        TextBlock(text="Continuous", x=10, y=10, width=80, height=20, translated="Refroidissement continu"),
        TextBlock(text="cooling", x=95, y=10, width=60, height=20, translated="Refroidissement continu"),
    ]
    asset = ImageAsset(url="file:///img.png", alt="img.png", position=0)
    results = [(asset, Path("out/fr/originals/img.png"), blocks)]

    _write_texts(tmp_path, "fr", results)

    content = (tmp_path / "texts.txt").read_text(encoding="utf-8")
    assert "## img.png" in content
    assert "[src]        Continuous cooling" in content
    assert "[fr] Refroidissement continu" in content
    # The shared translation appears once for the line, not once per block.
    assert content.count("Refroidissement continu") == 1
