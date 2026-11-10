"""init → review-page → 選択結果 → finalize → build を、LibreOffice を呼ばずに通す。
部品の見本（assets/components）を案に使う。"""

# ruff: noqa: S101  # pytest の assert
import json
import shutil
import subprocess

import pytest
from pptx import Presentation
from slide_maker import cli, lifecycle, paths

from tests._flow import finalize_all, write_choices, write_slide


@pytest.fixture
def comp(pkg):
    return pkg / "assets" / "components"


@pytest.fixture
def run(capsys):
    def _run(*argv):
        capsys.readouterr()
        rc = cli.main(list(argv))
        cap = capsys.readouterr()
        return rc, cap.out, cap.err

    return _run


def read(p):
    return p.read_text(encoding="utf-8")


@pytest.mark.slow
def test_全工程をLibreOfficeを呼ばずに通し_既存のPPTXは黙って上書きしない(tmp_path, monkeypatch, run, comp):
    calls = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def spy_run(cmd, *a, **k):
        calls.append(str(cmd[0] if isinstance(cmd, (list, tuple)) else cmd))
        return real_run(cmd, *a, **k)

    def spy_popen(cmd, *a, **k):
        calls.append(str(cmd[0] if isinstance(cmd, (list, tuple)) else cmd))
        return real_popen(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy_run)
    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    base = tmp_path / "out" / "slide-maker-source" / "demo"
    assert run("init", str(base))[0] == 0
    work = paths.resolve_work(base)
    slides = work / "slides"
    shutil.copyfile(comp / "layouts" / "cover.html", slides / "01-R1.html")
    shutil.copyfile(comp / "layouts" / "cover.html", slides / "01-R2.html")
    shutil.copyfile(comp / "tables" / "options.html", slides / "02-R1.html")
    shutil.copyfile(comp / "tables" / "actions.html", slides / "02-R2.html")
    shutil.copyfile(comp / "charts" / "bar.html", slides / "03-R1.html")
    shutil.copyfile(comp / "charts" / "bar.html", slides / "03-R2.html")

    assert run("review-page", str(base))[0] == 0
    page = read(work / "review.html")
    data = page.split('<script type="application/json" id="data">', 1)[1].split("</script>", 1)[0]
    assert [p[:2] for p in json.loads(data)] == [  # 3 つ目は案の特徴（data-variant）
        ["01", {"R1": read(slides / "01-R1.html"), "R2": read(slides / "01-R2.html")}],
        ["02", {"R1": read(slides / "02-R1.html"), "R2": read(slides / "02-R2.html")}],
        ["03", {"R1": read(slides / "03-R1.html"), "R2": read(slides / "03-R2.html")}],
    ]
    # 保存しただけ（承認していない）のページがあると、finalize は止まる
    ch = write_choices(tmp_path / "ch0", {"01": "R1", "02": "R2", "03": "R1"})
    saved = json.loads(read(ch / "choices" / "02.json")) | {"status": "saved"}
    (ch / "choices" / "02.json").write_text(json.dumps(saved), encoding="utf-8")
    rc, _, err = run("finalize", str(base), "--choices", str(ch))
    assert rc == 2, err
    assert "S02" in err
    assert not (work / "final.html").exists()
    # S02 は R2（対応一覧）が選ばれる
    ch = write_choices(tmp_path / "ch1", {"01": "R1", "02": "R2", "03": "R1"})
    assert run("finalize", str(base), "--choices", str(ch))[0] == 0
    final = read(work / "final.html")
    assert read(comp / "tables" / "actions.html") in final
    assert read(comp / "tables" / "options.html") not in final

    rc, out, _ = run("build", str(base))
    assert rc == 0, out
    result = json.loads(out)
    pptx = base.parent.parent / "demo.pptx"
    assert pptx.exists()
    assert len(Presentation(str(pptx)).slides) == 3
    assert [v for v in result["violations"] if v["severity"] == "error"] == []
    assert "final.html" in result["removed"]
    assert "review.html" in result["removed"]
    assert sorted(p.name for p in base.parent.parent.iterdir()) == ["demo.pptx", "slide-maker-source"]
    assert not (work / "theme.css").exists()
    assert result["previews"]

    lifecycle.prune(work)
    # 選び直し: 派生ファイルは finalize が作り直す
    ch = write_choices(tmp_path / "ch2", {"01": "R1", "02": "R1", "03": "R1"})
    assert run("finalize", str(base), "--choices", str(ch))[0] == 0
    assert (work / "theme.css").exists()
    assert read(comp / "tables" / "options.html") in read(work / "final.html")
    # 既存の PPTX を黙って上書きしない
    before = pptx.read_bytes()
    rc, _, err = run("build", str(base))
    assert rc == 4, err
    assert pptx.read_bytes() == before
    assert run("build", str(base), "--force")[0] == 0
    assert run("clean", str(base))[0] == 0

    assert [c for c in calls if "soffice" in c.lower() or "libreoffice" in c.lower()] == []


def test_build_stops_on_fourth_hue(tmp_path, run, comp):
    base = tmp_path / "out" / "slide-maker-source" / "demo"
    assert run("init", str(base))[0] == 0
    work = paths.resolve_work(base)
    html = read(comp / "layouts" / "text.html")
    boxes = "".join(
        f'<div class="pp-shape" style="left:{80 + 200 * i}px;top:560px;width:100px;height:30px;background:{c}"></div>'
        for i, c in enumerate(["#1E7A4A", "#B85A0B", "#0B6E99", "#7A3E9D"])
    )
    write_slide(work / "slides", "01", html.replace("</section>", boxes + "</section>"))
    assert finalize_all(work) == 0
    rc, out, _ = run("build", str(base))
    assert rc == 1, out
    assert "colorRange" in [v["rule"] for v in json.loads(out)["violations"]]
    assert not (base.parent.parent / "demo.pptx").exists()


def test_同梱の全部品がbuildを通り色と文字の規約で誤検出しない(tmp_path, run, comp):
    base = tmp_path / "out" / "slide-maker-source" / "demo"
    assert run("init", str(base))[0] == 0
    work = paths.resolve_work(base)
    parts = sorted(p for d in ("layouts", "charts", "tables") for p in (comp / d).glob("*.html"))
    for n, p in enumerate(parts, 1):
        write_slide(work / "slides", f"{n:02d}", read(p))
    assert finalize_all(work) == 0
    rc, out, _ = run("build", str(base))
    assert rc == 0, out
    assert [v for v in json.loads(out)["violations"] if v["severity"] == "error"] == []
