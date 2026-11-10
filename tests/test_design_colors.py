"""設計図（design.md）から基調色・強調色を取る。"""

# ruff: noqa: S101  # pytest の assert
import pytest
from pptx_deck import design_colors


def _work(tmp_path, text):
    (tmp_path / "design.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_reads_accent_and_emphasis_from_design_md(tmp_path):
    work = _work(tmp_path, "## 配色\n- 基調色: #1F3A5F\n- 強調色: #B85A0B, #0B6E99\n")
    p = design_colors.load(work, {})
    assert p.accent == "#1F3A5F"
    assert p.emphasis == "#B85A0B"
    budget = design_colors.chromatic_budget(p)
    assert {"#1F3A5F", "#B85A0B", "#0B6E99"} <= set(budget)


def test_old_cfg_color_is_used_when_design_has_no_colors(tmp_path):
    work = _work(tmp_path, "# 設計図\n")
    assert design_colors.load(work, {"color": "#1E6B52"}).accent == "#1E6B52"


def test_invalid_hex_raises(tmp_path):
    work = _work(tmp_path, "- 基調色: navy\n")
    with pytest.raises(ValueError, match="#RRGGBB"):
        design_colors.load(work, {})


def test_template_accent_used_last(tmp_path):
    work = _work(tmp_path, "# 設計図\n")
    assert design_colors.load(work, {}, ("#2A6F97",)).accent == "#2A6F97"


def test_default_navy(tmp_path):
    assert design_colors.load(tmp_path, {}).accent == "#1F3A5F"


def test_エラーに値の出どころが出る(tmp_path):
    with pytest.raises(ValueError, match="強調色"):
        design_colors.load(_work(tmp_path, "- 強調色: red\n"), {})
    with pytest.raises(ValueError, match="template.json"):
        design_colors.load(_work(tmp_path, "# 設計図\n"), {"color": "navy"})
