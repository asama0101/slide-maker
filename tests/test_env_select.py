"""専用 venv の Python の選択（env.select_python）・調査結果のキャッシュ・調査スクリプト・
venv の作成（env.setup）・doctor。

置き換えるのは外部だけ: venv の Python を起動して調べる subprocess.run（調査と更新時刻の取得）と、
pip・chromium の導入コマンド（subprocess.call）。
キャッシュの読み書き・結果の判定・ファイルの扱いは実物を通す。
"""

# ruff: noqa: S101  # pytest の assert
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from slide_maker import cli, env

PKG = Path(__file__).resolve().parent.parent / "plugins" / "slide-maker"

GOOD = {
    "python": [3, 14],
    "versions": {"python-pptx": "1.0.2", "playwright": "1.52.0", "pymupdf": "1.28.2", "lxml": "6.1.3"},
    "chromium": True,
}


def bad(**over):
    d = {"python": [3, 14], "versions": dict(GOOD["versions"]), "chromium": True}
    d.update(over)
    return d


# ---- env.missing ----


def test_すべてそろっていれば不足はない():
    assert env.missing(GOOD) == []


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        (bad(versions={**GOOD["versions"], "playwright": "1.40.0"}), ["playwright 1.40.0（要 ==1.52.0）"]),
        (
            bad(versions={**GOOD["versions"], "pymupdf": None}, chromium=False),
            ["pymupdf が未導入です", "Playwright の chromium が使えません"],
        ),
        (bad(python=[3, 9]), ["Python 3.10 以上が必要です"]),
        (bad(versions={**GOOD["versions"], "lxml": "6.0.0"}), ["lxml 6.0.0（要 ==6.1.3）"]),
        (bad(versions={**GOOD["versions"], "lxml": "6.9.9"}), ["lxml 6.9.9（要 ==6.1.3）"]),
    ],
    ids=["版が違う", "未導入と_chromium_なし", "Python_が古い", "lxml_は古い版も不足", "lxml_は新しい版も不足"],
)
def test_要求と違うものが不足として挙がる(info, expected):
    assert env.missing(info) == expected


@pytest.mark.parametrize(("pkg_name", "spec"), sorted(env.REQUIREMENTS.items()), ids=sorted(env.REQUIREMENTS))
def test_要求する版はすべて_イコール2つで固定されている(pkg_name, spec):
    assert spec.startswith("==")
    assert spec[2:].replace(".", "").isdigit()


def test_要求するパッケージは4つ():
    assert sorted(env.REQUIREMENTS) == ["lxml", "playwright", "pymupdf", "python-pptx"]


def test_requirements_txt_は要求する版と同じ内容(pkg):
    lines = [x.strip() for x in (pkg / "requirements.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert sorted(lines) == ["lxml==6.1.3", "playwright==1.52.0", "pymupdf==1.28.2", "python-pptx==1.0.2"]


# ---- 外部コマンド（venv の Python の起動）の代わり ----


class FakeCommands:
    """subprocess.run の代わり。
    venv の Python に流す調査スクリプトと更新時刻のスクリプトに、決めた結果を返し、呼び出しを記録する。"""

    def __init__(self):
        self.info = GOOD
        self.infos = {}  # Python のパス → 調査結果（なければ info）
        self.stamp = [1, 2, 3]  # None なら、更新時刻の取得に失敗する
        self.calls = []

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append(list(cmd))
        if cmd[-1] == env._PROBE:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps(self.infos.get(str(cmd[0]), self.info)) + "\n", stderr=""
            )
        if cmd[-1] == env._STAMP and self.stamp is not None:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(self.stamp) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="failed")

    @property
    def probes(self):
        return [c for c in self.calls if c[-1] == env._PROBE]


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home"
    monkeypatch.setenv("SLIDE_MAKER_HOME", str(h))
    return h


@pytest.fixture
def vpy(home) -> Path:
    """置き場の下の専用 venv の python.exe（中身は使わない。更新時刻だけ見られる）。"""
    p = home / "venv" / "Scripts" / "python.exe"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    return p


@pytest.fixture
def cmds(monkeypatch) -> FakeCommands:
    fake = FakeCommands()
    monkeypatch.setattr(env.subprocess, "run", fake)
    return fake


# ---- select_python ----


def test_専用_venv_がそろっていればそれを選ぶ(vpy, cmds):
    sel = env.select_python()
    assert (sel.path, sel.missing) == (vpy, [])


def test_venv_がなければ何も起動せず仮想環境がないと返す(home, cmds):
    sel = env.select_python()
    assert sel.path is None
    assert sel.missing == ["仮想環境がありません"]
    assert cmds.calls == []


def test_版の古い_venv_は不足を挙げて選ばれない(vpy, cmds):
    cmds.info = bad(versions={**GOOD["versions"], "playwright": "1.40.0"})
    sel = env.select_python()
    assert sel.path is None
    assert sel.missing == ["playwright 1.40.0（要 ==1.52.0）"]


# ---- 専用 venv だけを使う ----


def test_run_uses_venv_python(vpy, cmds):
    """システムの Python（テストを動かしている Python）は調べず、専用 venv の Python を選ぶ。"""
    sel = env.select_python()
    assert sel.path == vpy
    assert {c[0] for c in cmds.calls} == {str(vpy)}
    assert str(vpy) != sys.executable


def test_doctor_reports_venv_only(home, cmds):
    cmds.info = bad(chromium=False)
    lines = env.diagnosis(env.select_python())
    assert "[NG] 仮想環境: ありません" in lines
    assert any("`setup --yes`" in x for x in lines)
    assert not any("システム" in x or "--system" in x for x in lines)


# ---- 調査結果のキャッシュ ----


def test_site_packages_の状態が変われば調べ直す(vpy, cmds):
    """束 F4 #15: pip upgrade や chromium の入れ替えで site-packages の状態が変われば、キャッシュは当たらない。"""
    env.select_python()
    env.select_python()
    assert len(cmds.probes) == 1
    cmds.stamp = [1, 99, 3]
    sel = env.select_python()
    assert (len(cmds.probes), sel.path) == (2, vpy)


def test_更新時刻を取れないときはキャッシュしない(vpy, cmds):
    cmds.stamp = None
    env.select_python()
    sel = env.select_python()
    assert (len(cmds.probes), sel.path) == (2, vpy)


def test_2回目の選択は調べ直さずキャッシュを使う(vpy, cmds):
    env.select_python()
    sel = env.select_python()
    assert (len(cmds.probes), sel.path) == (1, vpy)


def test_python_exe_の更新時刻が変われば調べ直す(vpy, cmds):
    env.select_python()
    st = vpy.stat()
    os.utime(vpy, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    sel = env.select_python()
    assert (len(cmds.probes), sel.path) == (2, vpy)


def test_壊れたキャッシュは無視して調べ直し_書き直す(vpy, home, cmds):
    env.select_python()
    cache = [f for f in home.iterdir() if f.is_file()]
    assert len(cache) == 1
    cache[0].write_text("{not json", encoding="utf-8")
    sel = env.select_python()
    assert (len(cmds.probes), sel.path) == (2, vpy)
    json.loads(cache[0].read_text(encoding="utf-8"))  # 正しい JSON に書き直されている
    env.select_python()
    assert len(cmds.probes) == 2


def test_書いたキャッシュに_schema_version_1_が入る(vpy, home, cmds):
    env.select_python()
    saved = json.loads((home / "probe-cache.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == 1


@pytest.mark.parametrize("schema", [None, 0, 2, "1"], ids=["なし", "0", "別の版", "文字列"])
def test_schema_version_がない_または違うキャッシュは捨てて調べ直し_書き直す(vpy, home, cmds, schema):
    env.select_python()
    cache = home / "probe-cache.json"
    saved = json.loads(cache.read_text(encoding="utf-8"))
    if schema is None:
        del saved["schema_version"]
    else:
        saved["schema_version"] = schema
    cache.write_text(json.dumps(saved), encoding="utf-8")  # 中身（entries）は有効なまま
    sel = env.select_python()
    assert (len(cmds.probes), sel.path) == (2, vpy)
    assert json.loads(cache.read_text(encoding="utf-8"))["schema_version"] == 1
    env.select_python()
    assert len(cmds.probes) == 2  # 書き直したキャッシュは使われる


def test_不足のある結果はキャッシュせず_そろった結果だけを残す(vpy, cmds):
    cmds.info = bad(chromium=False)
    assert env.select_python().path is None
    assert env.select_python().path is None
    assert len(cmds.probes) == 2
    cmds.info = GOOD
    assert env.select_python().path == vpy
    assert len(cmds.probes) == 3


def test_refresh_は必ず調べ直してキャッシュを更新する(vpy, cmds):
    env.select_python()
    env.select_python(refresh=True)
    assert len(cmds.probes) == 2
    env.select_python()
    assert len(cmds.probes) == 2  # refresh で更新したキャッシュを使う


def test_refresh_で不足が見つかれば古い成功のキャッシュを捨てる(vpy, cmds):
    env.select_python()
    cmds.info = bad(chromium=False)
    assert env.select_python(refresh=True).path is None
    assert env.select_python().path is None
    assert len(cmds.probes) == 3  # 古い「そろっている」キャッシュが残っていれば 2 回で済んでしまう


def test_キャッシュを書けなくても選択は成功し一時ファイルも残らない(vpy, home, cmds):
    (home / "probe-cache.json").mkdir()  # キャッシュの置き場所をフォルダでふさぐ
    sel = env.select_python()
    assert sel.path == vpy
    assert sorted(p.name for p in home.iterdir()) == ["probe-cache.json", "venv"]


# ---- 更新時刻の取得と調査スクリプト（実際に起動する） ----


def test_更新時刻は実際の_python_から4つの値のリストで取れる():
    st = env._stamp(Path(sys.executable))
    assert isinstance(st, list)
    assert len(st) == 4
    assert isinstance(st[0], int)  # site-packages の更新時刻


def _run_probe(tmp_path, pw_version):
    """偽の playwright（起動すると目印のファイルを作る）を PYTHONPATH に置いて _PROBE を実際に実行する。"""
    t = tmp_path / "fake"
    (t / "playwright").mkdir(parents=True)
    (t / "playwright" / "__init__.py").write_text("", encoding="utf-8")
    marker = t / "started.txt"
    fake = "\n".join(
        [
            "from pathlib import Path",
            "class _P:",
            "    class chromium:",
            f"        executable_path = {str(marker)!r}",
            "    def stop(self): pass",
            "def sync_playwright():",
            "    class S:",
            "        def start(self):",
            f"            Path({str(marker)!r}).write_text('1')",
            "            return _P()",
            "    return S()",
        ]
    )
    (t / "playwright" / "sync_api.py").write_text(fake, encoding="utf-8")
    di = t / f"playwright-{pw_version}.dist-info"
    di.mkdir()
    meta = "\n".join(["Metadata-Version: 2.1", "Name: playwright", f"Version: {pw_version}", ""])
    (di / "METADATA").write_text(meta, encoding="utf-8")
    r = subprocess.run(  # noqa: S603  # 自分の探査コードを sys.executable で起動する（外部入力なし）
        [sys.executable, "-c", env._PROBE], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(t)}
    )
    return json.loads(r.stdout.strip().splitlines()[-1]), marker.exists()


@pytest.mark.parametrize(
    ("pw_version", "started", "chromium"),
    [("0.0.1", False, False), ("1.52.0", True, True)],
    ids=["版が違えば_chromium_を起動しない", "要求する版なら_chromium_を起動して確かめる"],
)
def test_調査スクリプトは_playwright_の版が合うときだけ_chromium_を起動する(tmp_path, pw_version, started, chromium):
    info, was_started = _run_probe(tmp_path, pw_version)
    assert info["versions"]["playwright"] == pw_version
    assert was_started is started
    assert info["chromium"] is chromium


# ---- setup ----


@pytest.fixture
def commands_run(monkeypatch) -> list:
    """subprocess.call（pip・chromium の導入。ネットワークを使う外部コマンド）の代わり。
    呼ばれたコマンドを記録して成功を返す。"""
    run = []
    monkeypatch.setattr(env.subprocess, "call", lambda cmd, *a, **k: run.append(list(cmd)) or 0)
    return run


@pytest.fixture
def spaced_home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home 日本語"  # 空白・日本語を含む置き場でも動く
    monkeypatch.setenv("SLIDE_MAKER_HOME", str(h))
    return h


def test_承認なしの_setup_は何も作らず案内して終了コード3(spaced_home, commands_run, capsys):
    rc = env.setup(yes=False)
    assert rc == 3
    assert not spaced_home.exists()
    assert commands_run == []
    assert str(spaced_home / "venv") in capsys.readouterr().out


@pytest.mark.slow
def test_承認ありの_setup_は置き場の下に_venv_を作り_pip_と_chromium_を順に導入する(
    spaced_home, commands_run, pkg, capsys
):
    rc = env.setup(yes=True)
    assert rc == 0
    py = spaced_home / "venv" / "Scripts" / "python.exe"
    assert py.is_file()
    assert commands_run == [
        [str(py), "-m", "pip", "install", "-r", str(pkg / "requirements.txt")],
        [str(py), "-m", "playwright", "install", "chromium"],
    ]
    assert str(spaced_home / "venv") in capsys.readouterr().out


def test_作成元の_python_が古ければ_setup_は何も作らず終了コード3(spaced_home, commands_run, monkeypatch, capsys):
    with monkeypatch.context() as m:
        m.setattr(env.sys, "version_info", (3, 9, 0))
        rc = env.setup(yes=True)
    assert rc == 3
    assert "3.10" in capsys.readouterr().out
    assert not spaced_home.exists()
    assert commands_run == []


def test_作成元の_python_に問題がなければ空(monkeypatch):
    assert env.base_python_problems() == []


def test_ensurepip_が無ければ_venv_を作れないと報告する(monkeypatch):
    real = env.importlib.util.find_spec
    with monkeypatch.context() as m:
        m.setattr(env.importlib.util, "find_spec", lambda n: None if n == "ensurepip" else real(n))
        problems = env.base_python_problems()
    assert problems == ["Python 標準ライブラリの ensurepip が使えません（venv を作れません）"]


def test_python_が3_10_未満なら問題として報告する(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(env.sys, "version_info", (3, 9, 0))
        problems = env.base_python_problems()
    assert problems == ["Python 3.10 以上が必要です（今は 3.9）"]


# ---- doctor ----


def test_doctor_は専用_venv_の置き場と実行中の_python_のパスを出す(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLIDE_MAKER_HOME", str(tmp_path))
    assert cli.main(["doctor"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(x.startswith(f"[OK] 仮想環境: {tmp_path / 'venv'}") for x in lines)
    assert any(x.startswith("[OK] 実行環境: Python ") and sys.executable in x for x in lines)
    assert f"[OK] 保存先: {tmp_path}（書き込めます）" in lines
    assert lines[0] == "[OK] OS: Windows"
    font = [x for x in lines if "BIZ UDPゴシック" in x][0]
    assert font.startswith("[OK]" if cli._font_installed() else "[任意]")  # フォントがなければ任意の項目として出る
