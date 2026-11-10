# ruff: noqa: S101  # pytest の assert
"""案を選ぶ Artifact ページへのローカル画像の埋め込み（review_page.build）のテスト。"""

import base64
import re
from pathlib import Path

import pytest
from pptx_deck import review_page

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))


def _work(tmp_path: Path, frag: str, name: str = "01-R1.html") -> Path:
    s = tmp_path / "slides"
    s.mkdir(exist_ok=True)
    (s / name).write_text(frag, encoding="utf-8")
    other = s / name.replace("R1", "R2") if "R1" in name else s / name.replace("R2", "R1")
    if not other.exists():  # 案は 2 つ要るので、もう一方は画像のない詰め物にする
        other.write_text("<div>x</div>", encoding="utf-8")
    (tmp_path / "theme.css").write_text(":root{--bg:#fff;}", encoding="utf-8")
    (tmp_path / "base.css").write_text(".pp-text{color:red}", encoding="utf-8")
    (tmp_path / "chart-preview.js").write_text("window.__chartPreview=function(){};", encoding="utf-8")
    return tmp_path


def _material(work: Path, name: str, data: bytes = PNG) -> None:
    (work / "material").mkdir(exist_ok=True)
    (work / "material" / name).write_bytes(data)


def _html(work: Path) -> str:
    """断片は JSON の中に入るので、引用符のエスケープを戻して返す。"""
    return review_page.build(work).read_text(encoding="utf-8").replace('\\"', '"')


def test_img_src_becomes_data_uri(tmp_path):
    work = _work(tmp_path, '<img class="pp-image" src="material/a.png" alt="x">')
    _material(work, "a.png")
    html = _html(work)
    assert "material/a.png" not in html
    m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)
    assert m
    assert base64.b64decode(m.group(1)) == PNG


@pytest.mark.parametrize(
    ("ext", "mime"),
    [
        ("jpg", "image/jpeg"),
        ("jpeg", "image/jpeg"),
        ("gif", "image/gif"),
        ("webp", "image/webp"),
        ("svg", "image/svg+xml"),
    ],
)
def test_mime_by_extension(tmp_path, ext, mime):
    work = _work(tmp_path, f'<img src="material/a.{ext}">')
    _material(work, f"a.{ext}")
    assert f"data:{mime};base64," in _html(work)


def test_svg_image_href_and_xlink_href(tmp_path):
    frag = '<div class="pp-picture"><svg><image href="material/a.png"/><image xlink:href="material/a.png"/></svg></div>'
    work = _work(tmp_path, frag)
    _material(work, "a.png")
    html = _html(work)
    assert "material/a.png" not in html
    assert html.count("data:image/png;base64,") == 2
    assert 'xlink:href="data:image/png' in html


def test_other_references_untouched(tmp_path):
    frag = (
        '<img src="data:image/png;base64,AAAA"><img src="https://example.com/a.png">'
        '<img src="http://example.com/b.png"><img src="file:///C:/x.png">'
        '<svg><use href="#id"/><image href="#id"/></svg>'
    )
    html = _html(_work(tmp_path, frag))
    for s in (
        "data:image/png;base64,AAAA",
        "https://example.com/a.png",
        "http://example.com/b.png",
        "file:///C:/x.png",
        'href="#id"',
    ):
        assert s in html


def test_missing_file_is_error(tmp_path):
    work = _work(tmp_path, '<img src="material/none.png">')
    with pytest.raises(ValueError, match=r"material/none\.png"):
        review_page.build(work)


def test_outside_work_folder_is_error(tmp_path):
    (tmp_path / "w").mkdir()
    work = _work(tmp_path / "w", '<img src="../x.png">')
    (tmp_path / "x.png").write_bytes(PNG)
    with pytest.raises(ValueError, match=r"\.\./x\.png"):
        review_page.build(work)


def test_unsupported_extension_is_error(tmp_path):
    work = _work(tmp_path, '<img src="material/a.bmp">')
    _material(work, "a.bmp")
    with pytest.raises(ValueError, match=r"a\.bmp"):
        review_page.build(work)


def test_all_errors_reported_at_once(tmp_path):
    work = _work(tmp_path, '<img src="material/one.png"><img src="material/two.png">')
    with pytest.raises(ValueError, match="画像を埋め込めません") as e:
        review_page.build(work)
    assert "one.png" in str(e.value)
    assert "two.png" in str(e.value)
    assert "01" in str(e.value)


def test_gt_inside_quoted_attribute(tmp_path):
    work = _work(tmp_path, '<img alt="a>b" src="material/a.png">')
    _material(work, "a.png")
    html = _html(work)
    assert "material/a.png" not in html
    assert '<img alt="a>b" src="data:image/png;base64,' in html


def test_oversize_reports_embedded_image_size(tmp_path, monkeypatch):
    """同じ画像を 2 つの案で使うと、ページには 2 回入る。画像の大きさは入った分を数える。"""
    big = PNG + bytes(300_000)
    work = _work(tmp_path, '<img src="material/a.png">', "01-R1.html")
    _work(tmp_path, '<img src="material/a.png">', "01-R2.html")
    _material(work, "a.png", big)
    monkeypatch.setattr(review_page, "MAX_PAGE_BYTES", 1000)
    one = len("data:image/png;base64,") + len(base64.b64encode(big))
    with pytest.raises(ValueError, match=f"うち画像が {2 * one / 1048576:.1f} MiB です"):
        review_page.build(work)


def test_same_file_in_two_candidates(tmp_path):
    work = _work(tmp_path, '<img src="material/a.png">', "01-R1.html")
    _work(tmp_path, '<img src="material/a.png">', "01-R2.html")
    _material(work, "a.png")
    assert _html(work).count("data:image/png;base64,") == 2
