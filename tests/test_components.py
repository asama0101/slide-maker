"""部品の見本（assets/components）: 残した断片が検査を通り、デザイン違い・不要なアイコンが残っていない。"""

# ruff: noqa: S101  # pytest の assert
import json
import re

import pytest
from pptx_deck import check, initdir, measure, paths, template

from tests._paths import PKG

COMP = PKG / "assets" / "components"
ICONS = PKG / "assets" / "icons"
KEPT = sorted(COMP.glob("*/*.html"))


@pytest.mark.slow
def test_every_kept_fragment_passes_check(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    info = template.TemplateInfo.from_dict(json.loads((work / "template.json").read_text(encoding="utf-8"))["info"])
    assert len(KEPT) == 16
    bad = []
    for f in KEPT:
        (work / "final.html").write_text(
            '<!doctype html><html lang="ja"><head><meta charset="utf-8"><link rel="stylesheet" href="theme.css">'
            '<link rel="stylesheet" href="base.css"></head><body>' + f.read_text(encoding="utf-8") + "</body></html>",
            encoding="utf-8",
        )
        bad += [
            (f.relative_to(COMP).as_posix(), v["rule"])
            for v in check.check_model(measure.measure(work / "final.html"), info)
            if v["severity"] == "error"
        ]
    assert bad == []


def test_no_design_variants_remain():
    assert [f.name for f in COMP.rglob("*") if re.search(r"-d[23]\.html$", f.name)] == []


def test_icons_referenced_exist():
    names = {f.stem for f in ICONS.glob("*.svg")}
    assert len(names) <= 30
    refs = set()
    for f in [*KEPT, *(PKG / "references").glob("*.md")]:
        refs |= set(
            re.findall(r"icons/([a-z][a-z-]*?)-(?:accent|emphasis|white|gray)\.svg", f.read_text(encoding="utf-8"))
        )
    assert refs - names == set()
    listed = set(re.findall(r"^\| `([a-z-]+)` \|", (PKG / "references" / "icons.md").read_text(encoding="utf-8"), re.M))
    assert listed == names
