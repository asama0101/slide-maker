"""check_model が返す規則を、はみ出し・重なり・文字の欠落・禁止領域・文字サイズの 5 つに絞ったことの確認。
ブラウザなしで動く（モデルは手で組む）。"""

# ruff: noqa: S101  # pytest の assert
import pytest
from pptx_deck import charts, check, cli, paths, template

REMOVED = {
    "contrast",
    "titleMissing",
    "imageAlt",
    "bodyImage",
    "imageSrc",
    "pictureSvg",
    "pictureOverflow",
    "pictureColor",
    "pictureTextOverlap",
    "dash",
    "sameWord",
    "orphanLine",
    "emptyBand",
    "leadMissing",
    "leadLength",
    "titleLength",
    "chartSpec",
}


def _info():
    return template.analyze(paths.ASSETS / "template" / "standard.potx")


def _text(idx, x, y, w, h, text="本文", size_px=24, **kw):
    box = {"x": x, "y": y, "w": w, "h": h}
    el = {
        "kind": "text",
        "idx": idx,
        "role": None,
        "ph": None,
        "chrome": False,
        "overlap": False,
        "bg": "FFFFFF",
        "box": box,
        "rect": box,
        "paras": [{"runs": [{"text": text, "size_px": size_px, "color": "000000"}]}],
    }
    el.update(kw)
    return el


def _rules(elements, layout="content"):
    model = [{"index": 1, "layout": layout, "bg": "FFFFFF", "elements": elements}]
    return {v["rule"] for v in check.check_model(model, _info())}


def test_overflow_overlap_keepout_fontmin_remain():
    assert _rules([_text(0, 80, 120, 400, 50, overflow=True)]) == {"overflow"}
    assert _rules([_text(0, 80, 120, 400, 50, lost="消えた文字")]) == {"textLost"}
    assert _rules([_text(0, 80, 120, 400, 50), _text(1, 200, 130, 400, 50)]) == {"overlap"}
    assert _rules([_text(0, 80, 120, 400, 50, size_px=16)]) == {"fontMin"}  # 12pt は本文の下限 14pt 未満
    assert _rules([_text(0, 80, 690, 400, 28)]) == {"keepout"}  # フッターの領域
    assert _rules([_text(0, 1200, 120, 400, 50)]) == {"outOfSlide"}  # スライドの外へのはみ出し


def test_removed_rules_not_reported():
    dirty = [
        _text(0, 80, 120, 400, 50, text="A―B と A―B と A―B", lastLineChars=1),
        _text(1, 80, 200, 400, 50, text="A―B と A―B と A―B"),
        {
            "kind": "image",
            "idx": 2,
            "src": "https://example.com/a.png",
            "alt": "",
            "rect": {"x": 600, "y": 300, "w": 600, "h": 400},
            "overlap": False,
        },
        {
            "kind": "picture",
            "idx": 3,
            "alt": "",
            "hasSvg": False,
            "badColors": ["#ff0000"],
            "texts": [{"text": "小さい", "size_px": 8, "rect": {"x": 0, "y": 0, "w": 10, "h": 10}}],
            "rect": {"x": 80, "y": 400, "w": 300, "h": 100},
            "overlap": False,
        },
        {
            "kind": "chart",
            "idx": 4,
            "chart": {"type": "area"},
            "rect": {"x": 700, "y": 100, "w": 100, "h": 100},
            "overlap": False,
        },
    ]
    dirty[0]["paras"][0]["runs"][0]["color"] = "FFFFFF"  # 白地に白（コントラスト不足）
    assert not _rules(dirty) & REMOVED  # タイトル・ヘッドメッセージなしの本文でも出ない


def test_invalid_chart_spec_stops_with_message():
    """不正な data-chart は check の違反ではなく、build が例外にして止める（誤ったグラフを黙って出さない）。"""
    with pytest.raises(ValueError, match=r"^未対応のグラフ型: area（bar, .*waterfall.*）$"):
        charts.add_chart(None, {"chart": {"type": "area"}, "rect": {}}, None)


def test_existing_pptx_requires_force(tmp_path, capsys):
    base = tmp_path / "out" / "pptx-deck-source" / "deck"
    assert cli.main(["init", str(base)]) == 0
    work = paths.resolve_work(base)
    (work / "final.html").write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(b"old")
    capsys.readouterr()
    assert cli.main(["build", str(base), "--out", str(pptx)]) == 4
    err = capsys.readouterr().err
    assert "--force" in err
    assert "--out" in err
    assert pptx.read_bytes() == b"old"
