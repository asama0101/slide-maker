"""派生ファイルの整理（prune）と再生成（ensure_derived）。"""

# ruff: noqa: S101  # pytest の assert
import re

from slide_maker import initdir, lifecycle

from tests._flow import write_slide


def test_pruneは既知の派生ファイルだけを消す(tmp_path):
    w = tmp_path
    for n in lifecycle.DERIVED_FILES:
        (w / n).write_text("x", encoding="utf-8")
    (w / "icons").mkdir()
    (w / "icons" / "a.svg").write_text("x", encoding="utf-8")
    (w / "_template").mkdir()
    (w / "_template" / "template.potx").write_bytes(b"t")
    for keep in (
        "design.md",
        "script.md",
        "template.json",
        "build.json",
        "answers-1.md",
        "round-2-notes.md",
        "素材メモ.md",
    ):
        (w / keep).write_text("k", encoding="utf-8")
    (w / "slides").mkdir()
    write_slide(w / "slides", "01", "s")
    removed = lifecycle.prune(w)
    assert "final.html" in removed
    assert "icons" in removed
    assert sorted(p.name for p in w.iterdir()) == sorted(
        [
            "_template",
            "answers-1.md",
            "build.json",
            "design.md",
            "round-2-notes.md",
            "script.md",
            "slides",
            "template.json",
            "素材メモ.md",
        ]
    )
    assert [p.name for p in (w / "_template").iterdir()] == ["template.potx"]
    assert (w / "slides" / "01-R1.html").read_text(encoding="utf-8") == "s"


def test_空のフォルダをpruneしても何も消えず落ちない(tmp_path):
    assert lifecycle.prune(tmp_path) == []


def test_theme_cssに文字サイズの変数がなければensure_derivedが作り直す(tmp_path):
    work = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(work)
    css = work / "theme.css"
    css.write_text(
        re.sub(r"^.*--(fs|num|chart)-.*\n", "", css.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8"
    )
    assert "--fs-title" not in css.read_text(encoding="utf-8")
    assert lifecycle.ensure_derived(work) is True
    assert "--fs-title" in css.read_text(encoding="utf-8")
    assert lifecycle.ensure_derived(work) is False


def test_design_mdの基調色が変わるとensure_derivedがtheme_cssを作り直す(tmp_path):
    work = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(work)
    assert lifecycle.ensure_derived(work) is False
    design = work / "design.md"
    design.write_text(design.read_text(encoding="utf-8") + "\n- 基調色: #1E6B52\n", encoding="utf-8")
    assert lifecycle.ensure_derived(work) is True
    assert re.search(r"--accent:\s*#1E6B52", (work / "theme.css").read_text(encoding="utf-8"), re.I)
    assert lifecycle.ensure_derived(work) is False


def test_強調色だけ変えるとensure_derivedがtheme_cssとアイコンを作り直す(tmp_path):
    work = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(work)
    design = work / "design.md"
    design.write_text("- 基調色: #1F3A5F\n- 強調色: #B85A0B\n", encoding="utf-8")
    assert lifecycle.ensure_derived(work) is True
    design.write_text("- 基調色: #1F3A5F\n- 強調色: #7A3E9D\n", encoding="utf-8")
    assert lifecycle.ensure_derived(work) is True
    assert "--emphasis: #7A3E9D;" in (work / "theme.css").read_text(encoding="utf-8")
    icon = next((work / "icons").glob("*-emphasis.svg"))
    assert "#7A3E9D" in icon.read_text(encoding="utf-8")


def test_rules_jsonのsize_pxが変わるとensure_derivedが作り直す(tmp_path):
    work = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(work)
    (work / "rules.json").write_text('{"lead": {"size_px": 30}}', encoding="utf-8")
    assert lifecycle.ensure_derived(work) is True
    assert "--fs-lead: 30px;" in (work / "theme.css").read_text(encoding="utf-8")
