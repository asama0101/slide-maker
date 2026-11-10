"""色の範囲・蛍光色・文字のコントラストの検査。ブラウザなしで動く（モデルは手で組む）。"""

# ruff: noqa: S101  # pytest の assert
from pptx_deck import check, paths, template, theme


def _info():
    return template.analyze(paths.ASSETS / "template" / "standard.potx")


def _text(idx, color="1A1A1A", x=80, y=120):
    box = {"x": x, "y": y, "w": 300, "h": 50}
    return {
        "kind": "text",
        "idx": idx,
        "role": None,
        "ph": None,
        "chrome": False,
        "overlap": False,
        "box": box,
        "rect": box,
        "paras": [{"runs": [{"text": "本文", "size_px": 24, "color": color}]}],
    }


def _shape(idx, fill, x=80, y=300):
    rect = {"x": x, "y": y, "w": 100, "h": 50}
    return {
        "kind": "shape",
        "idx": idx,
        "shape": "rect",
        "chrome": False,
        "ph": None,
        "overlap": True,
        "rect": rect,
        "fill": {"hex": fill.lstrip("#"), "a": 1},
        "line": None,
    }


def _rules(elements, palette=None):
    model = [{"index": 1, "layout": "content", "bg": "FFFFFF", "elements": elements}]
    out = check.check_model(model, _info(), palette)
    return [v["rule"] for v in out if v["rule"].startswith("color")]


PAL = theme.derive("#1F3A5F")


def test_three_hue_groups_pass():
    els = [_shape(0, PAL.accent), _shape(1, PAL.accent_mid, x=300), _shape(2, PAL.accent_soft, x=500)]
    els += [_shape(3, PAL.emphasis, x=700), _shape(4, "#1E7A4A", x=900)]
    assert _rules(els, PAL) == []


def test_fourth_hue_fails():
    els = [_shape(i, c, x=80 + 200 * i) for i, c in enumerate(["#1E7A4A", "#B85A0B", "#0B6E99", "#7A3E9D"])]
    assert _rules(els, PAL) == ["colorRange"]


def test_gray_only_passes():
    els = [_shape(0, "#808080"), _text(1, "1A1A1A"), _shape(2, "#D9DEE3", x=400)]
    assert _rules(els, PAL) == []


def test_tints_of_accent_are_one_group():
    els = [_shape(0, "#1F3A5F")] + [
        _shape(i + 1, theme.tint("#1F3A5F", t), x=200 * (i + 1)) for i, t in enumerate((0.3, 0.5, 0.8))
    ]
    assert _rules(els, PAL) == []


def test_neon_fails():
    assert "colorNeon" in _rules([_shape(0, "#00FF00")], PAL)


def test_low_contrast_text_fails():
    assert _rules([_text(0, "BBBBBB")], PAL) == ["colorContrast"]


def test_text_on_fill_uses_fill():
    # 濃い面の上の白い文字は読める
    panel = _shape(0, "#1F3A5F", x=60, y=100)
    panel["rect"] = {"x": 60, "y": 100, "w": 400, "h": 100}
    assert _rules([panel, _text(1, "FFFFFF")], PAL) == []


def test_no_palette_skips_color_rules():
    assert _rules([_text(0, "BBBBBB")]) == []


def _deck(*slides):
    model = [
        {"index": i, "layout": "content", "bg": "FFFFFF", "elements": [_shape(0, c) for c in cs]}
        for i, cs in enumerate(slides, start=1)
    ]
    return [v for v in check.check_model(model, _info(), PAL) if v["rule"] == "colorRange"]


def test_hue_budget_is_deck_wide():
    v = _deck([PAL.accent], ["#1E7A4A"], ["#B85A0B"], ["#7A3E9D"])
    assert len(v) == 1
    assert v[0]["slide"] == 4


def test_accent_and_emphasis_across_slides_pass():
    assert _deck([PAL.accent], [PAL.accent_mid, PAL.emphasis], [PAL.accent_soft, "#1E7A4A"], [PAL.accent]) == []


# --- 最終レビューの修正 ---
PAL2 = theme.derive("#1E6B52", "#B85A0B")


def _deck2(els, pal=PAL2, layout="content", backgrounds=None):
    model = [{"index": 1, "layout": layout, "elements": els}]
    out = check.check_model(model, _info(), pal, None, backgrounds)
    return [v["rule"] for v in out if v["rule"].startswith("color")]


def test_自前の灰色と淡いパネルは色の系統に数えない():
    els = [_shape(0, PAL2.accent), _shape(1, PAL2.emphasis, x=200), _shape(2, "#0B6E99", x=400)]
    els += [_shape(3, "#D9DEE3", x=600), _shape(4, "#EEF3F6", x=800)]
    assert "colorRange" not in _deck2(els)


def test_四色目があればcolorRangeが出る():
    els = [_shape(0, PAL2.accent), _shape(1, PAL2.emphasis, x=200), _shape(2, "#0B6E99", x=400)]
    els += [_shape(3, "#7A3E9D", x=600)]
    assert "colorRange" in _deck2(els)


def test_色の順序を入れ替えても結果が同じ():
    cols = [PAL2.emphasis, "#0B6E99", "#7A3E9D", PAL2.accent, "#D9DEE3"]
    a = [_shape(i, c, x=100 * i) for i, c in enumerate(cols)]
    b = [_shape(i, c, x=100 * i) for i, c in enumerate(reversed(cols))]
    model = lambda els: [{"index": 1, "layout": "content", "elements": els}]  # noqa: E731
    ra = [v for v in check.check_model(model(a), _info(), PAL2) if v["rule"] == "colorRange"]
    rb = [v for v in check.check_model(model(b), _info(), PAL2) if v["rule"] == "colorRange"]
    assert ra
    assert ra == rb
    assert "#7A3E9D" in ra[0]["message"]
    assert PAL2.accent not in ra[0]["message"].split("超えた色:")[1]


def test_暗い表紙の背景に白い題は違反にならない():
    assert _deck2([_text(0, "FFFFFF")], layout="cover", backgrounds={"cover": "#1F3A5F", "body": "#FFFFFF"}) == []
    assert _deck2([_text(0, "FFFFFF")], layout="content", backgrounds={"cover": "#1F3A5F", "body": "#FFFFFF"}) == [
        "colorContrast"
    ]


def test_淡い塗りは下の背景と合成してコントラストを測る():
    panel = _shape(0, "#1F3A5F", x=60, y=100)
    panel["rect"] = {"x": 60, "y": 100, "w": 400, "h": 100}
    panel["fill"]["a"] = 0.1
    assert _deck2([panel, _text(1, "1A1A1A")]) == []


def test_本当に低いコントラストは違反になる():
    assert _deck2([_text(0, "BBBBBB")]) == ["colorContrast"]


def test_写真の上の文字はコントラストを検査しない():
    img = {
        "kind": "image", "idx": 0, "chrome": False, "ph": None, "overlap": True,
        "rect": {"x": 60, "y": 100, "w": 400, "h": 100},
    }  # fmt: skip
    assert _deck2([img, _text(1, "FFFFFF")]) == []


def test_明示した強調色も白地で4_5以上になる(tmp_path):
    from pptx_deck import design_colors

    p = theme.derive("#1F3A5F", "#ED7D31")
    assert theme.contrast(p.emphasis, "#FFFFFF") >= 4.5
    design = "- 基調色: #1F3A5F\n- 強調色: #ED7D31, #4BACC6\n"
    (tmp_path / "design.md").write_text(design, encoding="utf-8")
    q = design_colors.load(tmp_path, {})
    assert theme.contrast(q.emphasis, "#FFFFFF") >= 4.5
    assert theme.contrast(q.emphasis_extra[0], "#FFFFFF") >= 4.5
