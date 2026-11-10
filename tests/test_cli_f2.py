"""再監査 F2: entry の例外処理（#11・#22）、init --force（#16）、ensure_derived（#25）、
run.py の stderr（#29）、build --out（#30）。"""

# ruff: noqa: S101  # pytest の assert
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from slide_maker import cli, initdir, lifecycle, paths

from tests._flow import write_slide

PKG = Path(__file__).resolve().parent.parent / "plugins" / "slide-maker"
STANDARD_POTX = PKG / "assets" / "template" / "standard.potx"


@pytest.fixture
def no_browser(monkeypatch):
    """Playwright を読み込めなくする。測定（ブラウザの起動）まで進んだら ModuleNotFoundError になる。"""
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)


def entry(capsys, *argv):
    capsys.readouterr()
    rc = cli.entry(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def custom_template(dst: Path) -> Path:
    """標準テンプレートに余分なエントリを足して、標準とバイト列が違う（利用者の）テンプレートを作る。"""
    with zipfile.ZipFile(STANDARD_POTX) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("docProps/marker.txt", "custom")
    return dst


@pytest.fixture
def base(tmp_path) -> Path:
    """標準テンプレートで init した成果物の置き場。"""
    b = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(b)
    return b


# ---- entry の例外処理 ----


def test_存在しない原稿の_lint_script_は終了コード2で案内する(tmp_path, capsys):
    rc, _, err = entry(capsys, "lint-script", str(tmp_path / "nai.md"))
    assert rc == 2
    assert "エラー" in err
    assert "nai.md" in err


def test_init_が書き込めない場所なら終了コード2で案内する(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")  # ファイルの下にはフォルダを作れない
    rc, _, err = entry(capsys, "init", str(blocker / "deck"))
    assert rc == 2
    assert "エラー" in err
    assert blocker.read_text(encoding="utf-8") == "x"


def test_依存のモジュールが無いときは終了コード3で不足しているモジュール名を案内する(base, no_browser, capsys):
    work = paths.resolve_work(base)
    html = work / "a.html"
    html.write_text("<html></html>", encoding="utf-8")
    rc, out, _ = entry(capsys, "check", str(html))  # 測定で playwright を読み込む
    assert rc == 3
    assert "playwright" in out


def test_check_は存在しない_html_なら測定せず終了コード2で止まる(base, no_browser, capsys):
    work = paths.resolve_work(base)
    rc, out, err = entry(capsys, "check", str(work / "nai.html"))
    assert rc == 2  # 測定まで進めば playwright が無く 3 になる
    assert "エラー" in err
    assert out == ""


# ---- init --force とテンプレート ----


def test_利用者のテンプレートが消えた成果物の_force_は_template_を求めて終了コード2で止まる(tmp_path, capsys):
    b = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(b, template_path=custom_template(tmp_path / "own.potx"))
    work = paths.resolve_work(b)
    assert paths.read_cfg(work)["custom_template"] is True
    (work / paths.read_cfg(work)["template"]).unlink()
    with pytest.raises(ValueError, match="--template"):
        initdir.init(b, force=True)
    rc, _, err = entry(capsys, "init", str(b), "--force")
    assert rc == 2
    assert "--template" in err


def test_標準テンプレートが消えた成果物の_force_は標準テンプレートを作り直す(base):
    work = paths.resolve_work(base)
    assert paths.read_cfg(work)["custom_template"] is False
    (work / paths.read_cfg(work)["template"]).unlink()
    initdir.init(base, force=True)
    cfg = paths.read_cfg(work)
    assert (work / cfg["template"]).read_bytes() == STANDARD_POTX.read_bytes()
    assert cfg["custom_template"] is False


def test_force_で作り直しても利用者のテンプレートの印が残り_消えたら求める(tmp_path):
    b = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(b, template_path=custom_template(tmp_path / "own.potx"))
    work = paths.resolve_work(b)
    initdir.init(b, force=True)
    assert paths.read_cfg(work)["custom_template"] is True
    (work / paths.read_cfg(work)["template"]).unlink()
    with pytest.raises(ValueError, match="--template"):
        initdir.init(b, force=True)


def test_標準テンプレートを明示して_init_しても利用者のテンプレート扱いにならない(tmp_path):
    b = tmp_path / "out" / "slide-maker-source" / "deck"
    initdir.init(b, template_path=STANDARD_POTX)
    assert paths.read_cfg(paths.resolve_work(b))["custom_template"] is False


def test_テンプレートの記録がない古い成果物でテンプレートが消えたら_force_は_template_を求める(base):
    work = paths.resolve_work(base)  # 記録のない古い作業フォルダは、利用者のテンプレートかもしれないので止める
    cfg = paths.read_cfg(work)
    del cfg["custom_template"]
    paths.write_cfg(work, cfg)
    (work / cfg["template"]).unlink()
    with pytest.raises(ValueError, match="--template"):
        initdir.init(base, force=True)


def test_テンプレートが消えていても_template_を渡せば_force_で復旧できる(base):
    work = paths.resolve_work(base)
    template = work / paths.read_cfg(work)["template"]
    template.unlink()
    initdir.init(base, force=True, template_path=STANDARD_POTX)
    assert template.read_bytes() == STANDARD_POTX.read_bytes()


# ---- ensure_derived ----


def test_消えた_chart_preview_js_は_ensure_derived_で作り直される(base):
    work = paths.resolve_work(base)
    original = (work / "chart-preview.js").read_bytes()
    (work / "chart-preview.js").unlink()
    assert lifecycle.ensure_derived(work) is True
    assert (work / "chart-preview.js").read_bytes() == original
    assert lifecycle.ensure_derived(work) is False  # そろっていれば何もしない


# ---- run.py の標準出力・標準エラー ----


@pytest.mark.parametrize(
    ("argv", "stream", "expected"),
    [
        ([], "stdout", "専用の仮想環境の置き場が指定されていません"),
        (["--data", "rel", "doctor"], "stderr", "エラー: --data は絶対パスで指定してください"),
    ],
    ids=["標準出力_置き場なし", "標準エラー_相対パス"],
)
def test_run_py_は端末が_cp932_でも標準出力と標準エラーを_UTF8_で書く(argv, stream, expected, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("SLIDE_MAKER_HOME", "PYTHONUTF8")}
    env["PYTHONIOENCODING"] = "cp932"
    # S603: 自分の入口を sys.executable で起動する（外部入力なし）
    r = subprocess.run([sys.executable, str(PKG / "run.py"), *argv], capture_output=True, env=env, cwd=tmp_path)  # noqa: S603
    assert expected in getattr(r, stream).decode("utf-8")


# ---- build --out の種類 ----


@pytest.fixture
def deck_with_final(base) -> Path:
    work = paths.resolve_work(base)
    write_slide(work / "slides", "01", "<section class='slide'></section>")
    (work / "final.html").write_text("<html></html>", encoding="utf-8")
    return work


def test_出力先がフォルダなら測定の前に終了コード2で止まる(deck_with_final, tmp_path, no_browser, capsys):
    d = tmp_path / "outdir"
    d.mkdir()
    capsys.readouterr()
    rc = cli.main(["build", str(deck_with_final), "--out", str(d), "--force"])
    cap = capsys.readouterr()
    assert rc == 2
    assert ".pptx" in cap.err
    assert cap.out == ""
    assert list(d.iterdir()) == []


def test_出力先の拡張子が_pptx_でなければ測定の前に終了コード2で止まる(deck_with_final, tmp_path, no_browser, capsys):
    out = tmp_path / "a.html"
    capsys.readouterr()
    rc = cli.main(["build", str(deck_with_final), "--out", str(out)])
    cap = capsys.readouterr()
    assert rc == 2
    assert ".pptx" in cap.err
    assert cap.out == ""
    assert not out.exists()
