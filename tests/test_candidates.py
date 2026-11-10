# ruff: noqa: S101  # pytest の assert
"""案の収集（candidates.collect）のテスト。"""

import re
from pathlib import Path

import pytest
from pptx_deck import candidates


def _put(work: Path, *names: str, body: str = "<div>x</div>") -> Path:
    d = work / "slides"
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text(body + n, encoding="utf-8")
    return work


def _put_all(work: Path, *nns: str) -> Path:
    return _put(work, *[f"{nn}-R{k}.html" for nn in nns for k in (1, 2)])


def test_collect_accepts_R1_R2(tmp_path):
    _put(tmp_path, "01-R1.html", "01-R2.html")
    assert candidates.collect(tmp_path) == {"01": {"R1": "<div>x</div>01-R1.html", "R2": "<div>x</div>01-R2.html"}}


def test_collect_rejects_A(tmp_path):
    _put(tmp_path, "01-A.html")
    with pytest.raises(ValueError, match="01-A.html: 型のページも 2〜3 案（01-R1.html〜）にしてください"):
        candidates.collect(tmp_path)


def test_collect_requires_two_variants(tmp_path):
    _put(tmp_path, "01-R1.html", "01-R2.html", "02-R1.html")
    with pytest.raises(ValueError, match="02: 2〜3 案"):
        candidates.collect(tmp_path)


def test_collect_free_page(tmp_path):
    _put(tmp_path, "01-R1.html", "01-R2.html")
    assert list(candidates.collect(tmp_path)["01"]) == ["R1", "R2"]


def test_collect_free_page_three(tmp_path):
    _put(tmp_path, "01-R1.html", "01-R2.html", "01-R3.html")
    assert list(candidates.collect(tmp_path)["01"]) == ["R1", "R2", "R3"]


def test_rejects_design_suffix(tmp_path):
    _put(tmp_path, "02-R1.html", "02-R2.html", "02-R1-d2.html")
    with pytest.raises(ValueError, match="-d2"):
        candidates.collect(tmp_path)


def test_rejects_single_free(tmp_path):
    _put(tmp_path, "04-R1.html")
    with pytest.raises(ValueError, match="04: 2〜3 案（04-R1.html〜04-R3.html のうち 2〜3 個）が要ります"):
        candidates.collect(tmp_path)


def test_free_page_accepts_gap(tmp_path):
    _put(tmp_path, "01-R1.html", "01-R3.html")
    assert list(candidates.collect(tmp_path)["01"]) == ["R1", "R3"]


@pytest.mark.parametrize("bad", ["02-R1.HTML", "s02-R1.html", "S02-R1.html", "2-R1.html", "02-r1.html", "02_R1.html"])
def test_digit_names_not_matching_are_reported(tmp_path, bad):
    _put(tmp_path, "01-R1.html", "01-R2.html", bad)
    with pytest.raises(ValueError, match=f"読めないファイルがあります: {re.escape(bad)}（旧形式"):
        candidates.collect(tmp_path)


@pytest.mark.parametrize(
    "other", ["notes.html", "README.HTML", "draft-1.html", "memo2.html", "v2-notes.html", "R1.html"]
)
def test_html_not_starting_with_number_is_ignored(tmp_path, other):
    _put(tmp_path, "01-R1.html", "01-R2.html", other)
    assert list(candidates.collect(tmp_path)) == ["01"]


def test_rejects_four_free(tmp_path):
    _put(tmp_path, "04-R1.html", "04-R2.html", "04-R3.html", "04-R4.html")
    with pytest.raises(ValueError, match="R4"):
        candidates.collect(tmp_path)


def test_old_names(tmp_path):
    _put(tmp_path, "05-R.html", "05-B.html")
    with pytest.raises(ValueError, match=r"(?s)05-B.*05-R.*旧形式"):
        candidates.collect(tmp_path)


def test_errors_are_reported_together(tmp_path):
    _put(tmp_path, "03-R1.html", "04-R1.html")
    with pytest.raises(ValueError, match=r"(?s)03.*04"):
        candidates.collect(tmp_path)


def test_missing_slides_dir(tmp_path):
    with pytest.raises(ValueError, match="slides"):
        candidates.collect(tmp_path)


def test_svg_ids_unique_per_candidate(tmp_path):
    svg = '<div class="pp-picture"><svg><defs><marker id="m"/></defs><path marker-end="url(#m)"/></svg></div>'
    _put(tmp_path, "01-R1.html", "01-R2.html", body=svg)
    got = candidates.collect(tmp_path)["01"]
    assert 'id="m"' not in got["R1"]
    assert 'id="s01r1-m"' in got["R1"]
    assert 'id="s01r2-m"' in got["R2"]


def test_rejects_gap_in_numbers(tmp_path):
    _put_all(tmp_path, "01", "02", "04", "06")
    with pytest.raises(ValueError, match="スライド番号が連続していません。足りない番号: 03, 05"):
        candidates.collect(tmp_path)


def test_rejects_numbers_not_starting_at_01(tmp_path):
    _put_all(tmp_path, "02", "03")
    with pytest.raises(ValueError, match="足りない番号: 01$"):
        candidates.collect(tmp_path)


def test_gap_is_reported_with_other_errors(tmp_path):
    _put_all(tmp_path, "01")
    _put(tmp_path, "03-R1.html")
    with pytest.raises(ValueError, match=r"(?s)2〜3 案.*足りない番号: 02"):
        candidates.collect(tmp_path)


def test_rejects_number_00(tmp_path):
    _put_all(tmp_path, "00", "01")
    with pytest.raises(ValueError, match="01 から始めます"):
        candidates.collect(tmp_path)


def test_warns_text_only_variant():
    cands = {"03": {"R1": '<div class="pp-chart"></div>', "R2": '<div class="pp-text">x</div>'}}
    assert candidates.main_visual_warnings(cands, set()) == ["03-R2: 図・絵・表・グラフが主役になっていません"]


def test_exempt_page_not_warned():
    cands = {"01": {"R1": '<div class="pp-text">題</div>', "R2": '<div class="pp-text">題</div>'}}
    assert candidates.main_visual_warnings(cands, {"01"}) == []


def test_main_visual_class_is_matched_by_word():
    cands = {"01": {"R1": '<div class="x pp-table">', "R2": '<div class="pp-tablet">'}}
    assert candidates.main_visual_warnings(cands, set()) == ["01-R2: 図・絵・表・グラフが主役になっていません"]


def test_アイコンの画像は主役の図表に数えない():
    icon = '<img class="pp-image" data-role="icon" src="icons/a.svg" alt="">'
    photo = '<img class="pp-image" data-role="photo" src="p.png" alt="">'
    assert candidates.main_visual_warnings({"02": {"R1": icon, "R2": photo}}, set()) == [
        "02-R1: 図・絵・表・グラフが主役になっていません"
    ]
