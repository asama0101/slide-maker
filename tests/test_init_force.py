"""init --force は、明示しなかったフッター・テンプレートを保つ。"""

# ruff: noqa: S101  # pytest の assert
import json
import zipfile
from pathlib import Path

import pytest
from pptx_deck import cli, initdir, paths


def _custom_template(dst: Path) -> Path:
    """標準テンプレートに余分なエントリを足して、標準とバイト列が違うテンプレートを作る。"""
    src = paths.ASSETS / "template" / "standard.potx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("docProps/marker.txt", "custom")
    return dst


def _cfg(work: Path) -> dict:
    return json.loads((work / "template.json").read_text(encoding="utf-8"))


@pytest.fixture
def deck(tmp_path):
    """独自テンプレート・フッターつきで init した作業フォルダ。(base, work, 独自テンプレートのバイト列)"""
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    tpl = _custom_template(tmp_path / "other.potx")
    initdir.init(base, template_path=tpl, footer="© 2026 A")
    work = paths.resolve_work(base)
    tbytes = tpl.read_bytes()
    assert tbytes != (paths.ASSETS / "template" / "standard.potx").read_bytes()
    assert (work / _cfg(work)["template"]).read_bytes() == tbytes
    return base, work, tbytes


def test_forceだけならフッター_テンプレートを保つ(deck):
    base, work, tbytes = deck
    initdir.init(base, force=True)
    after = _cfg(work)
    assert after["footer"] == "© 2026 A"
    assert (work / after["template"]).read_bytes() == tbytes


def test_CLIのforceだけならフッター_テンプレートを保つ(deck):
    base, work, tbytes = deck
    assert cli.main(["init", str(base), "--force"]) == 0
    after = _cfg(work)
    assert after["footer"] == "© 2026 A"
    assert (work / after["template"]).read_bytes() == tbytes


def test_新規のinitは標準テンプレート_フッターなし(tmp_path):
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(base)
    work = paths.resolve_work(base)
    cfg = _cfg(work)
    assert "color" not in cfg
    assert cfg["footer"] is None
    assert (work / cfg["template"]).read_bytes() == (paths.ASSETS / "template" / "standard.potx").read_bytes()


def test_テンプレートの色が設計図に色の行がないとき基調色になる(tmp_path):
    from pptx_deck import design_colors, template, theme

    work = tmp_path / "out" / "pptx-deck-source" / "deck"
    r = initdir.init(work)
    cfg = paths.read_cfg(work)
    accents = template.accent_colors(work / cfg["template"])
    assert r["template_accents"] == list(accents)
    assert accents
    assert design_colors.load_for(work, cfg).accent == theme.derive(accents[0]).accent


def test_旧形式の色はinit_forceで引き継がれる(tmp_path):
    from pptx_deck import design_colors

    work = tmp_path / "out" / "pptx-deck-source" / "deck"
    initdir.init(work)
    (work / "design.md").unlink()
    cfg = paths.read_cfg(work)
    cfg["color"] = "#1E6B52"
    paths.write_cfg(work, cfg)
    initdir.init(work, force=True)
    new = paths.read_cfg(work)
    assert new["color"] == "#1E6B52"
    assert design_colors.load_for(work, new).accent == "#1E6B52"
