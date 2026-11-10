"""題・ヘッドメッセージの規約（rules.json）と chromeSpec 検査。"""

# ruff: noqa: S101  # pytest の assert
import pytest
from slide_maker import check, paths, rules, template


def test_defaults_match_fontsize(tmp_path):
    r = rules.load(tmp_path)
    assert r["title"]["size_px"] == 37
    assert r["lead"]["size_px"] == 27
    assert r["title"]["font"] == "BIZ UDPゴシック"
    assert r["title"]["align"] == "left"


def test_rules_json_overrides_one_field(tmp_path):
    (tmp_path / "rules.json").write_text('{"lead": {"size_px": 30}}', encoding="utf-8")
    r = rules.load(tmp_path)
    assert r["lead"]["size_px"] == 30
    assert r["lead"]["font"] == "BIZ UDPゴシック"
    assert r["title"]["size_px"] == 37


@pytest.mark.parametrize("body", ["{broken", '{"foo": {}}', '{"title": {"color": "red"}}'])
def test_broken_json_raises(tmp_path, body):
    (tmp_path / "rules.json").write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match="rules.json"):
        rules.load(tmp_path)


def _model(size=30, family="BIZ UDPゴシック", align="left"):
    box = {"x": 80, "y": 40, "w": 900, "h": 50}
    el = {
        "kind": "text", "idx": 0, "role": "title", "ph": None, "chrome": False, "overlap": False,
        "box": box, "rect": box, "family": family,
        "paras": [{"align": align, "runs": [{"text": "題", "size_px": size, "color": "1A1A1A"}]}],
    }  # fmt: skip
    return [{"index": 1, "elements": [el]}]


def _info():
    return template.analyze(paths.ASSETS / "template" / "standard.potx")


def _spec(tmp_path):
    return rules.load(tmp_path)


def test_chromespec_flags_wrong_title_size(tmp_path):
    v = check.check_model(_model(30), _info(), rules=_spec(tmp_path))
    assert [x["rule"] for x in v if x["rule"] == "chromeSpec"] == ["chromeSpec"]


def test_chromespec_uses_override(tmp_path):
    (tmp_path / "rules.json").write_text('{"title": {"size_px": 30}}', encoding="utf-8")
    v = check.check_model(_model(30), _info(), rules=_spec(tmp_path))
    assert not [x for x in v if x["rule"] == "chromeSpec"]


def test_chromespec_flags_font_and_align(tmp_path):
    v = check.check_model(_model(37, "Meiryo", "center"), _info(), rules=_spec(tmp_path))
    assert len([x for x in v if x["rule"] == "chromeSpec"]) == 1
    assert "フォント" in v[-1]["message"] or any("配置" in x["message"] for x in v)


def test_chromespec_accepts_css_english_font_name(tmp_path):
    v = check.check_model(_model(37, "BIZ UDPGothic"), _info(), rules=_spec(tmp_path))
    assert not [x for x in v if x["rule"] == "chromeSpec"]


def test_font_を書くとエラー(tmp_path):
    (tmp_path / "rules.json").write_text('{"title": {"font": "Meiryo"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="固定"):
        rules.load(tmp_path)


def test_size_pxはtheme_cssに反映され検査も通る(tmp_path):
    from slide_maker import initdir

    work = tmp_path / "out" / "slide-maker-source" / "deck"
    work.mkdir(parents=True)
    (work / "rules.json").write_text('{"title": {"size_px": 32}}', encoding="utf-8")
    initdir.init(work, force=True)
    css = (work / "theme.css").read_text(encoding="utf-8")
    assert "--fs-title: 32px;" in css
    assert "--fs-lead: 27px;" in css
    v = check.check_model(_model(32), _info(), rules=rules.load(work))
    assert not [x for x in v if x["rule"] == "chromeSpec"]
