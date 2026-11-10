"""監査の指摘 1・3・7 の再現テスト。ブラウザなしで動く（モデルは手で組む）。"""

# ruff: noqa: S101  # pytest の assert
import json
import re

import pytest
from pptx import Presentation
from pptx_deck import build, paths, templatestore


def test_build_は作業フォルダの外の画像を貼らない(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (tmp_path / "secret.png").write_bytes(b"x")
    el = {"src": "../secret.png", "alt": "a", "rect": {"x": 0, "y": 0, "w": 10, "h": 10}}
    with pytest.raises(ValueError, match="作業フォルダの外"):
        build.add_image(None, el, work, "w")


# ---- 3: 名前の規則を 1 つにする ----
@pytest.mark.parametrize("name", ["CON", "nul", "COM1", "CON.x"])
def test_テンプレートの名前に予約名は使えない(name):
    with pytest.raises(ValueError, match="予約名"):
        templatestore.check_name(name)


@pytest.mark.parametrize("name", ["CON", "a:b", "x."])
def test_テンプレート名は使えない文字と末尾のドットを弾く(name):
    with pytest.raises(ValueError, match="使えません"):
        templatestore.check_name(name)


def test_予約名のテンプレートは何も置かれない(tmp_path, monkeypatch):
    monkeypatch.setenv("PPTX_DECK_HOME", str(tmp_path / "home"))
    prs = Presentation()
    prs.slide_width, prs.slide_height = 12192000, 6858000
    src = tmp_path / "t.pptx"
    prs.save(str(src))
    with pytest.raises(ValueError, match="予約名"):
        templatestore.import_template(src, "CON")
    assert not (tmp_path / "home" / "templates").exists()


# ---- 7: JSON の書き込み ----
def test_write_json_は一時ファイルを残さず_重ならない名前で書く(tmp_path):
    paths.write_json(tmp_path / "x.json", {"a": "あ"})
    paths.write_json(tmp_path / "x.json", {"a": "い"})
    assert json.loads((tmp_path / "x.json").read_text(encoding="utf-8")) == {"a": "い"}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


# ---- 壊れた pp-image: OS のエラーでなく、画像とスライドの番号つきで止める ----
@pytest.mark.parametrize(("src", "shown"), [("material/none.png", "material/none.png"), ("", "(空)")])
def test_add_image_はない画像を番号つきのValueErrorにする(tmp_path, src, shown):
    el = {"idx": 3, "src": src, "alt": "a", "rect": {"x": 0, "y": 0, "w": 10, "h": 10}}
    with pytest.raises(ValueError, match=rf"^image#3: 画像 {re.escape(shown)} がありません$"):
        build.add_image(None, el, tmp_path, "w")


def test_build_の要素のエラーにスライド番号を付け_PPTX_を書かない(tmp_path):
    from pptx_deck import template

    from tests._paths import PKG

    std = PKG / "assets" / "template" / "standard.potx"
    img = {"kind": "image", "idx": 0, "src": "", "alt": "a", "rect": {"x": 0, "y": 0, "w": 10, "h": 10}}
    model = [
        {"index": 1, "layout": "content", "type": "", "elements": []},
        {"index": 2, "layout": "content", "type": "", "elements": [img]},
    ]
    out = tmp_path / "o.pptx"
    with pytest.raises(ValueError, match=r"^スライド 2: image#0: 画像 \(空\) がありません$"):
        build.build(model, std, template.analyze(std), None, out, base_dir=tmp_path)
    assert not out.exists()
