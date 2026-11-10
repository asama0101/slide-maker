import io
import json

import pytest
from slide_maker import update_check

REPO_URL = "https://github.com/asama0101/slide-maker"


@pytest.fixture
def root(tmp_path):
    """プラグインの根（plugin.json だけ置く）。CLAUDE_CONFIG_DIR は別の tmp に向ける。"""
    r = tmp_path / "plugin"
    (r / ".claude-plugin").mkdir(parents=True)
    (r / ".claude-plugin" / "plugin.json").write_text(json.dumps({"repository": REPO_URL}), encoding="utf-8")
    return r


def _register(tmp_path, monkeypatch, entries):
    cfg = tmp_path / "cfg"
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "plugins" / "known_marketplaces.json").write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))


def _github(repo):
    return {"slide-maker": {"source": {"source": "github", "repo": repo}}}


def _remote(monkeypatch, version):
    body = json.dumps({"version": version}).encode()
    monkeypatch.setattr(update_check, "urlopen", lambda url, timeout: io.BytesIO(body))


def test_登録がなければ何も調べない(root, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "none"))
    assert update_check.check("4.0.0", root) is None


def test_別のリポジトリの登録だけなら調べない(root, tmp_path, monkeypatch):
    _register(tmp_path, monkeypatch, _github("someone/else"))
    assert update_check.check("4.0.0", root) is None


def test_github_以外の登録は対象外(root, tmp_path, monkeypatch):
    _register(tmp_path, monkeypatch, {"slide-maker": {"source": {"source": "directory", "path": "x"}}})
    assert update_check.check("4.0.0", root) is None


@pytest.mark.parametrize(
    ("current", "latest", "ok"),
    [("4.0.0", "4.0.0", True), ("4.0.0", "4.1.0", False), ("4.0.0", "10.0.0", False), ("5.0.0", "4.9.9", True)],
)
def test_版を数として比べる(root, tmp_path, monkeypatch, current, latest, ok):
    _register(tmp_path, monkeypatch, _github("Asama0101/slide-maker"))
    _remote(monkeypatch, latest)
    assert update_check.check(current, root) == {"repo": "asama0101/slide-maker", "latest": latest, "up_to_date": ok}


def test_取得に失敗したらエラーを返す(root, tmp_path, monkeypatch):
    _register(tmp_path, monkeypatch, _github("asama0101/slide-maker"))

    def boom(url, timeout):
        raise OSError("offline")

    monkeypatch.setattr(update_check, "urlopen", boom)
    r = update_check.check("4.0.0", root)
    assert r["repo"] == "asama0101/slide-maker"
    assert "offline" in r["error"]
    assert "up_to_date" not in r
