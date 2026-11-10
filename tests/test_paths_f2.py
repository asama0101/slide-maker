"""再監査 F2: 一時フォルダの名前（#4）、resolve_work（#5）、write_cfg のアトミック化（#18）。"""

# ruff: noqa: S101  # pytest の assert
import json
import os
import re
import tempfile

import pytest
from pptx_deck import cli, paths


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    """OS の一時フォルダを tmp_path の下に向ける。"""
    root = tmp_path / "os-temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def test_同名で別の作業フォルダの一時フォルダは分かれ_同じ作業フォルダなら同じ場所(tmp_path, temp_root):
    a = tmp_path / "A" / "pptx-deck-source" / "提案"
    b = tmp_path / "B" / "pptx-deck-source" / "提案"
    da = paths.temp_dir("提案", a)
    db = paths.temp_dir("提案", b)
    assert da != db
    assert re.fullmatch(r"提案-[0-9a-f]{8}", da.name)  # 人が読める名前を先頭に残し、ハッシュ 8 桁を足す
    assert da.parent == temp_root / "pptx-deck"
    assert paths.temp_dir("提案", a) == da


def test_作業フォルダを渡しても不正な名前は拒否される(temp_root):
    with pytest.raises(ValueError, match="一時フォルダの名前が不正です"):
        paths.temp_dir("", temp_root / "x" / "pptx-deck-source" / "提案")


def test_clean_は同名の別の成果物の一時フォルダを消さない(tmp_path, temp_root, capsys):
    works = []
    for side in ("A", "B"):
        base = tmp_path / side / "pptx-deck-source" / "提案"
        assert cli.main(["init", str(base)]) == 0
        works.append(paths.resolve_work(base))
    marks = []
    for w in works:
        m = paths.temp_dir("提案", w) / "mark.txt"
        m.write_text("x", encoding="utf-8")
        marks.append(m)
    capsys.readouterr()
    assert cli.main(["clean", str(works[0])]) == 0
    assert json.loads(capsys.readouterr().out)["cleaned"] == str(marks[0].parent)
    assert not marks[0].exists()
    assert marks[1].read_text(encoding="utf-8") == "x"


def test_存在する作業フォルダはそのまま返る(tmp_path):
    x = tmp_path / "X" / "pptx-deck-source" / "提案"
    x.mkdir(parents=True)
    assert paths.resolve_work(x) == x.resolve()


def test_init_は渡した作業フォルダに直接作り_入れ子の_source_を作らない(tmp_path):
    x = tmp_path / "X" / "pptx-deck-source" / "提案"
    assert cli.main(["init", str(x)]) == 0
    assert (x / "template.json").exists()
    assert not (x / "source").exists()


def test_write_cfg_の置き換えに失敗しても旧いファイルが残り一時ファイルも残らない(tmp_path, monkeypatch):
    paths.write_cfg(tmp_path, {"a": 1})
    with monkeypatch.context() as m:
        m.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))  # ディスクの失敗を起こす
        with pytest.raises(OSError, match="boom"):
            paths.write_cfg(tmp_path, {"a": 2})
    assert paths.read_cfg(tmp_path) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["template.json"]


def test_write_cfg_は日本語をエスケープせずそのまま_UTF8_で書く(tmp_path):
    paths.write_cfg(tmp_path, {"footer": "© 日本語"})
    raw = (tmp_path / "template.json").read_bytes()
    assert "© 日本語".encode() in raw
    assert json.loads(raw)["footer"] == "© 日本語"
