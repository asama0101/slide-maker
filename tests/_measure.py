"""テスト用: 断片の HTML を section.slide（1280×720）に入れて測り、モデルを返す。"""

import tempfile
from pathlib import Path

from pptx_deck import measure

from tests._paths import PKG

_BASE_CSS = (PKG / "assets" / "web" / "base.css").read_text(encoding="utf-8")


def model_of(inner_html: str, extra_css: str = "") -> list[dict]:
    html = (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        f"<style>{_BASE_CSS}\n{extra_css}</style></head><body>"
        '<section class="slide" style="position:relative;width:1280px;height:720px">'
        f"{inner_html}</section></body></html>"
    )
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "m.html"
        f.write_text(html, encoding="utf-8")
        return measure.measure(f)
