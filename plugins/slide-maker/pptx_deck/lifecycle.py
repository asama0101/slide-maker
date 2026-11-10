"""派生ファイルの整理と、一時ファイルの削除。削除は既知の派生ファイルに限る。"""

import shutil
from pathlib import Path

from . import paths

DERIVED_FILES = (
    "review.html",
    "final.html",
    "theme.css",
    "base.css",
    "chart-preview.js",
)
DERIVED_DIRS = ("icons",)


def prune(work: Path) -> list[str]:
    """再生成できる派生ファイルだけを消す。元データ（slides/ など）と未知のファイルは消さない。消した相対パスを返す。"""
    work = Path(work)
    removed: list[str] = []
    for name in DERIVED_FILES:
        p = work / name
        if p.is_file():
            p.unlink()
            removed.append(name)
    for name in DERIVED_DIRS:
        p = work / name
        if p.is_dir():
            shutil.rmtree(p)
            removed.append(name)
    return removed


def clean_temp(name: str, work=None) -> Path:
    """一時フォルダを消し、そのパスを返す。temp_dir は作って返すので、存在しなくても安全。"""
    d = paths.temp_dir(name, work)
    shutil.rmtree(d, ignore_errors=True)
    return d


def ensure_derived(work: Path) -> bool:
    """build や確認ページが使う派生ファイルが欠けていれば、template.json から再生成する。再生成したら True。"""
    from . import design_colors, initdir, rules

    work = Path(work)
    cfg = paths.read_cfg(work)
    if all((work / n).exists() for n in ("theme.css", "base.css", "chart-preview.js", "icons")):
        css = paths.read_text(work / "theme.css")
        # 文字サイズの変数を持たない古い theme.css、設計図の色や rules.json の大きさと違う theme.css は作り直す
        p = design_colors.load_for(work, cfg)
        sizes = rules.load(work)
        wanted = (
            f"--accent: {p.accent};",
            f"--emphasis: {p.emphasis};",
            f"--fs-title: {sizes['title']['size_px']:g}px;",
            f"--fs-lead: {sizes['lead']['size_px']:g}px;",
        )
        if "--fs-title" in css and all(w in css for w in wanted):
            return False
    initdir.write_derived(work, cfg)
    return True
