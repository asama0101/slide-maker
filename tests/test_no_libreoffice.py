"""LibreOffice に依存しない: コードに soffice がなく、背景は単色だけで、確認画像は Playwright で撮る。"""

# ruff: noqa: S101  # pytest の assert
import json
import re

import pytest
from pptx_deck import initdir, paths, preview


def test_プラグインのコードに_soffice_がなく_render_py_もない(pkg):
    for f in (pkg / "pptx_deck").glob("*.py"):
        assert "soffice" not in f.read_text(encoding="utf-8"), f.name
    assert not (pkg / "pptx_deck" / "render.py").exists()


def test_initは単色の背景だけを作る(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "d"
    initdir.init(base)
    src = paths.resolve_work(base)
    css = (src / "theme.css").read_text(encoding="utf-8")
    assert "background-image" not in css
    assert re.search(r"--bg: #[0-9A-Fa-f]{6}", css)
    assert [p.name for p in (src / "_template").iterdir()] == ["template.potx"]
    assert "info" in json.loads((src / "template.json").read_text(encoding="utf-8"))


@pytest.mark.slow
def test_確認画像はスライド1枚につき1枚できる(tmp_path):
    html = tmp_path / "final.html"
    html.write_text(
        '<!doctype html><meta charset="utf-8"><style>.slide{position:relative;width:1280px;height:720px;'
        "background:#fff;margin:0 0 24px}</style>"
        '<section class="slide">A</section><section class="slide">B</section>',
        encoding="utf-8",
    )
    out = preview.screenshots(html, tmp_path / "out")
    assert [p.name for p in out] == ["slide-01.png", "slide-02.png"]
    for p in out:
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
