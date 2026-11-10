# ruff: noqa: S101  # pytest の assert
"""選択結果の読み込み（choices.load）のテスト。"""

import json

import pytest
from slide_maker import choices


def _put(base, name, data):
    d = base / "choices"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def test_load_reads_files_by_page_number(tmp_path):
    _put(tmp_path, "01.json", {"at": "2026-11-08T06:55:51.860Z", "comment": "", "pick": "R3", "status": "approved"})
    _put(tmp_path, "02.json", {"comment": " 直す ", "status": "saved"})
    assert choices.load(tmp_path) == {
        "01": {"pick": "R3", "comment": "", "status": "approved"},
        "02": {"pick": None, "comment": "直す", "status": "saved"},
    }


def test_load_requires_choices_folder(tmp_path):
    with pytest.raises(ValueError, match="choices"):
        choices.load(tmp_path)


def test_load_reports_broken_json(tmp_path):
    _put(tmp_path, "01.json", "{broken")
    with pytest.raises(ValueError, match="01.json"):
        choices.load(tmp_path)
