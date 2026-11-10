"""作業フォルダ（<出力先>/pptx-deck-source/<成果物名>）の初期化。"""

import filecmp
import shutil
from pathlib import Path

from . import design_colors, fontsize, paths, rules, template, theme

ICON_TONES = ("accent", "emphasis", "white", "gray")


def _write_icons(dst: Path, p: theme.Palette):
    src = paths.ASSETS / "icons"
    if not src.is_dir():
        return
    colors = {"accent": p.accent, "emphasis": p.emphasis, "white": "#FFFFFF", "gray": p.text_sub}
    dst.mkdir(parents=True, exist_ok=True)
    for svg in sorted(src.glob("*.svg")):
        text = svg.read_text(encoding="utf-8")
        for tone in ICON_TONES:
            (dst / f"{svg.stem}-{tone}.svg").write_text(text.replace("currentColor", colors[tone]), encoding="utf-8")


def write_derived(work: Path, cfg: dict) -> list[str]:
    """template.json の内容から、再生成できるファイル（theme.css・base.css・chart-preview.js・icons/）を書く。
    notes を返す。"""
    work = Path(work)
    palette = design_colors.load_for(work, cfg)
    info = template.TemplateInfo.from_dict(cfg["info"])
    colors, notes = template.background_colors(work / cfg["template"], info)
    sizes = fontsize.current()
    for key, spec in rules.load(work).items():  # rules.json の題・ヘッドメッセージの大きさを反映する
        sizes[key] = spec["size_px"]
    root = theme.theme_css(palette, fontsize.css(sizes))
    (work / "theme.css").write_text(root + template.layout_css(info, colors["body"], colors), encoding="utf-8")
    shutil.copyfile(paths.ASSETS / "web" / "base.css", work / "base.css")
    preview = paths.ASSETS / "web" / "chart-preview.js"
    if preview.exists():
        shutil.copyfile(preview, work / "chart-preview.js")
    _write_icons(work / "icons", palette)
    return notes


def _existing_cfg(work: Path) -> dict:
    """--force のとき、渡されなかった項目を残すために既存の template.json を読む。読めなければ空。"""
    try:
        return paths.read_cfg(work)
    except (OSError, ValueError):
        return {}


def init(workdir, template_path=None, force: bool = False, footer: str | None = None) -> dict:
    work = paths.resolve_work(workdir)  # <出力先>/pptx-deck-source/<成果物名>
    if work.exists() and any(work.iterdir()) and not force:
        raise FileExistsError(f"{work} は空ではありません。中身を確認し、上書きしてよければ --force を付けてください")
    old = _existing_cfg(work) if force else {}
    if footer is None:
        footer = old.get("footer")
    standard = paths.ASSETS / "template" / "standard.potx"
    custom = None  # 利用者のテンプレートか。None は src と標準の中身で決める
    if template_path:
        src = Path(template_path)
    else:
        kept = work / old["template"] if old.get("template") else None
        custom = old.get("custom_template")
        if kept is not None and not kept.is_file():
            if custom is not False:  # 利用者のテンプレート、または記録のない古い作業フォルダ。黙って標準に替えない
                raise ValueError(f"前のテンプレートが見つかりません（{kept}）。--template で指定してください")
            kept = None  # 標準テンプレートだった成果物は、標準から写し直す
        src = kept if kept is not None else standard
    info = template.analyze(src)  # 非 16:9 などもここで失敗
    if custom is None:
        custom = not filecmp.cmp(src, standard, shallow=False)
    work.mkdir(parents=True, exist_ok=True)
    tdir = work / "_template"
    tdir.mkdir(exist_ok=True)
    dst = tdir / f"template{src.suffix.lower()}"
    if not (dst.exists() and src.resolve() == dst.resolve()):  # 既存のテンプレートの再利用では写さない
        shutil.copyfile(src, dst)
    cfg = {
        "template": f"_template/{dst.name}",
        "info": info.to_dict(),
        "footer": footer,
        "custom_template": custom,
    }
    if old.get("color"):  # 旧形式の基調色を引き継ぐ（設計図に色の行がなければ design_colors が使う）
        cfg["color"] = old["color"]
    paths.write_cfg(work, cfg)
    design = work / "design.md"
    if not design.exists():  # 設計図の雛形。--force でも利用者が書いた設計図は上書きしない
        shutil.copyfile(paths.ASSETS / "sample" / "design.md", design)
    notes = list(info.notes) + write_derived(work, cfg)
    (work / "slides").mkdir(exist_ok=True)
    stale = [p for p in (work / "slides").iterdir()]
    if stale:  # 消さない。古い案が選択の候補に混ざるので、利用者に確認してもらう
        notes.append(
            f"slides/ に既存のファイルが {len(stale)} 個あります。前の作業の案が混ざるので、不要なら削除してください"
        )
    return {
        "workdir": str(work),
        "template": str(dst),
        "notes": notes,
        "layout_map": template.describe(work / cfg["template"], info),
        "template_accents": list(template.accent_colors(dst)),  # 設計図の基調色・強調色の候補
    }
