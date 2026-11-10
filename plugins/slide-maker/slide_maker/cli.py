import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import __version__, env, paths
from .review_page import CAPABILITIES


def _has_font(registered: list[str], family: str) -> bool:
    return any(family in name for name in registered)


def _registered_fonts() -> list[str]:
    """レジストリの登録名（全員向け・利用者向け）。TTC 内のファミリも登録名に並ぶ。"""
    import winreg

    names: list[str] = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as k:
                i = 0
                while True:
                    names.append(winreg.EnumValue(k, i)[0])
                    i += 1
        except OSError:
            pass
    return names


def _font_installed() -> bool:
    return _has_font(_registered_fonts(), "BIZ UDPGothic")


def _ensure_derived(work: Path) -> None:
    """template.json があれば、欠けた派生ファイル（prune 済みのもの）を再生成する。無ければ何もしない。"""
    if (work / "template.json").exists():
        from . import lifecycle

        lifecycle.ensure_derived(work)


def doctor_lines() -> list[str]:
    """doctor の出力。標準項目（OS・実行環境・保存先）、固有の依存、版の順。対処は次の行に `→`。"""
    lines = env.lead_lines(full=False)
    lines.append(f"[OK] 仮想環境: {paths.venv_dir()}（ライブラリ・chromium を含む）")
    if _font_installed():
        lines.append("[OK] BIZ UDPゴシック: 導入済み")
    else:
        lines += [
            "[任意] BIZ UDPゴシック: 未導入（計測は代替フォントで行うため、PowerPoint で折り返しがずれる場合がある）",
            "  → BIZ UDPゴシックを導入する（使わなくても動く）",
        ]
    return lines + env.version_lines()


def cmd_doctor(args) -> int:
    lines = doctor_lines()
    print("\n".join(lines))
    return 3 if any(x.startswith("[NG]") for x in lines) else 0


def cmd_init(args) -> int:
    from . import initdir

    try:
        r = initdir.init(Path(args.workdir), template_path=args.template, force=args.force, footer=args.footer)
    except (FileExistsError, ValueError, OSError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def _template_store(action) -> int:
    """テンプレートの置き場の操作。使えないものは 2、同じ名前があれば 4。結果は JSON で出す。"""
    from . import templatestore

    try:
        result = action(templatestore)
    except FileExistsError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 4
    except (ValueError, OSError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_template_import(args) -> int:
    return _template_store(lambda s: s.import_template(args.path, args.name, args.force))


def cmd_template_list(args) -> int:
    return _template_store(lambda s: s.list_templates())


def cmd_template_remove(args) -> int:
    return _template_store(lambda s: s.remove_template(args.name))


def _no_cfg(work: Path) -> int | None:
    """作業フォルダに template.json がなければ案内を出して 2 を返す（あれば None）。"""
    if (work / "template.json").exists():
        return None
    print(f"エラー: {work} に template.json がありません（成果物の元データが見つかりません）", file=sys.stderr)
    return 2


def _load_cfg(work: Path):
    from . import design_colors, template

    cfg = paths.read_cfg(work)
    return cfg, template.TemplateInfo.from_dict(cfg["info"]), design_colors.load_for(work, cfg)


def _backgrounds(work: Path, cfg: dict, info) -> dict[str, str]:
    from . import template

    return template.background_colors(work / cfg["template"], info)[0]


def _load_rules(work: Path):
    from . import rules

    return rules.load(work)


def cmd_check(args) -> int:
    from . import check, measure

    html = Path(args.html)
    if not html.is_file():
        print(f"エラー: {html} がありません", file=sys.stderr)
        return 2
    work = paths.resolve_work(args.workdir) if args.workdir else html.parent
    if code := _no_cfg(work):
        return code
    cfg, info, palette = _load_cfg(work)
    violations = check.check_model(
        measure.measure(html), info, palette, _load_rules(work), _backgrounds(work, cfg, info)
    )
    print(json.dumps(violations, ensure_ascii=False, indent=2))
    return 1 if check.errors(violations) else 0


def _check_writable(out: Path) -> str | None:
    """出力先に書けるかを、測定の前に確かめる。書けなければ案内の文を返す。
    既存の PPTX は追記モードで開いて閉じるだけ（中身を変えない）。
    なければ親フォルダを作り、同じ場所に作った一時ファイルで確かめる（out は作らない）。"""
    hint = "PowerPoint で開いていれば閉じてください"
    try:
        if out.exists():
            with out.open("ab"):
                pass
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=out.parent):
                pass
    except OSError as e:
        return f"{out} に書き込めません（{e}）。{hint}。"
    return None


def cmd_build(args) -> int:
    from . import build, check, lifecycle, measure, preview

    work = paths.resolve_work(args.workdir)
    if code := _no_cfg(work):
        return code
    _ensure_derived(work)
    name = paths.deck_name(work)
    try:
        tkey = paths.temp_key(
            name, work
        )  # 確認用の画像の置き場の名前を、書き出す前に確かめる（作業フォルダごとに分ける）
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    cfg, info, palette = _load_cfg(work)
    html = work / "final.html"
    if not html.exists():
        print("エラー: final.html がありません（先に finalize を実行してください）", file=sys.stderr)
        return 2
    default_out = paths.deck_dir(work) / f"{name}.pptx"
    out = Path(args.out).resolve() if args.out else default_out
    if out.is_dir() or out.suffix.lower() != ".pptx":
        print(f"エラー: --out には .pptx のファイル名を指定してください（{out}）", file=sys.stderr)
        return 2
    if out.exists() and not args.force:
        print(
            f"エラー: {out} は既に存在します。"
            "上書きしてよければ --force、別の名前で出すなら --out <パス> を付けてください。",
            file=sys.stderr,
        )
        return 4
    if msg := _check_writable(out):
        print(f"エラー: {msg}", file=sys.stderr)
        return 2
    with measure.open_browser() as browser:  # 測定と確認用の画像で Chromium を 1 つだけ起動する
        # 絵（pp-picture）は、ここで画像にする
        model = measure.measure(html, raster_dir=paths.temp_dir(tkey) / "picture", browser=browser)
        violations = check.check_model(model, info, palette, _load_rules(work), _backgrounds(work, cfg, info))
        result = {
            "ok": False,
            "violations": violations,
            "pptx": None,
            "previews": [],
            "removed": [],
            "notes": list(info.notes),
        }
        if check.errors(violations):
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        footer = args.footer if args.footer is not None else cfg.get("footer")
        try:
            build.build(model, work / cfg["template"], info, palette, out, base_dir=work, footer=footer, work_name=tkey)
        except ValueError as e:  # 不正な data-chart など。誤ったグラフを黙って出さず、PPTX は書かずに止める
            print(f"エラー: {e}", file=sys.stderr)
            return 2
        violations += check.check_pptx(out)
        result["violations"] = violations
        result["pptx"] = str(out)
        try:
            shots = preview.screenshots(html, paths.temp_dir(tkey) / "preview", browser=browser)
            result["previews"] = [str(p) for p in shots]
        except Exception as e:  # noqa: BLE001  # PPTX は出ている。確認用の画像だけ作れなかったことを知らせる
            result["notes"].append(f"確認用の画像を作れませんでした: {e}")
        result["ok"] = not check.errors(violations)
    if result["ok"]:
        result["removed"] = lifecycle.prune(work)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_clean(args) -> int:
    from . import lifecycle

    work = paths.resolve_work(args.workdir)
    name = paths.deck_name(work)
    try:
        target = lifecycle.clean_temp(name, work)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"cleaned": str(target)}, ensure_ascii=False))
    return 0


def cmd_finalize(args) -> int:
    from . import finalize

    if not args.choices:  # 引数の検査は、作業フォルダに触れる前に行う
        print(
            "エラー: --choices <フォルダ> を指定してください（Artifact の選択結果 choices/<NN>.json を含むフォルダ）",
            file=sys.stderr,
        )
        return 2
    work = paths.resolve_work(args.workdir)
    if code := _no_cfg(work):
        return code
    _ensure_derived(work)
    try:
        print(finalize.finalize(work, Path(args.choices)))
    except ValueError as e:
        print(f"エラー:\n{e}", file=sys.stderr)
        return 2
    return 0


def cmd_review_page(args) -> int:
    from . import candidates, review_page, script_lint

    work = paths.resolve_work(args.workdir)
    if code := _no_cfg(work):
        return code
    _ensure_derived(work)
    try:
        page = review_page.build(work)
        script = work / "script.md"
        exempt = script_lint.exempt_ids(paths.read_text(script)) if script.is_file() else set()
        warnings = candidates.main_visual_warnings(candidates.collect(work), exempt)
        print(json.dumps({"path": str(page), "warnings": warnings}, ensure_ascii=False))
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_lint_script(args) -> int:
    from . import script_lint

    md = paths.read_text(args.script)
    problems = script_lint.lint(md)
    for p in problems:
        print(p)
    for n in script_lint.title_notes(md):  # 題の抜けの案内は、エラーにしない（終了コードに影響しない）
        print(n)
    return 1 if problems else 0


def entry(argv: list[str]) -> int:
    """python -m slide_maker の入口。依存が足りない仮想環境では、traceback ではなく案内を出す。"""
    try:
        return main(argv)
    except ModuleNotFoundError as e:
        print(f"必要なモジュールがありません: {e.name}")
        print(
            "専用の仮想環境が壊れているか、依存が足りません。"
            '`python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" doctor` で確認し、'
            "利用者の承認後に `setup --yes`（同じ `--data` 付き）を実行してください。"
        )
        return 3
    except (
        ValueError,
        OSError,
    ) as e:  # 個別に捕まえていない入力の不備（ファイルがない・書けない・テンプレートが消えた等）
        print(f"エラー: {e}", file=sys.stderr)
        return 2


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="slide-maker")
    ap.add_argument("--version", action="version", version=f"slide-maker {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    p = sub.add_parser("init")
    p.add_argument("workdir")
    p.add_argument("--template", default=None, help="利用者の .potx / .pptx")
    p.add_argument(
        "--footer",
        default=None,
        help='左下に出すコピーライトの文字列（例: "© 2026 〇〇"）。省略すると空欄（--force なら既存の値を残す）',
    )
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("template-import", help="利用者のテンプレート（.potx / .pptx）を、名前を付けて置き場に登録する")
    p.add_argument("path")
    p.add_argument("--name", default=None, help="登録名。省略するとファイル名（拡張子なし）")
    p.add_argument("--force", action="store_true", help="同じ名前があれば置き換える")
    p.set_defaults(fn=cmd_template_import)
    sub.add_parser("template-list", help="登録済みのテンプレートの一覧").set_defaults(fn=cmd_template_list)
    p = sub.add_parser("template-remove", help="登録済みのテンプレートを消す（作成済みの成果物には影響しない）")
    p.add_argument("name")
    p.set_defaults(fn=cmd_template_remove)
    p = sub.add_parser("check")
    p.add_argument("html")
    p.add_argument("--workdir", default=None)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("build")
    p.add_argument("workdir")
    p.add_argument("--footer", default=None)
    p.add_argument("--out", default=None, help="PPTX の出力先（省略すると <出力先>/<成果物名>.pptx）")
    p.add_argument("--force", action="store_true", help="既存の PPTX を上書きする")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("clean")
    p.add_argument("workdir")
    p.set_defaults(fn=cmd_clean)
    p = sub.add_parser("finalize")
    p.add_argument("workdir")
    p.add_argument(
        "--choices",
        default=None,
        help="Artifact の選択結果。choices/<NN>.json を含むフォルダ（choices/ の親）を渡す（必須）",
    )
    p.set_defaults(fn=cmd_finalize)
    p = sub.add_parser(
        "review-page",
        help=f"案を選ぶ Artifact ページ（review.html）を作る（公開は capabilities: {json.dumps(CAPABILITIES)} が要る）",
    )
    p.add_argument("workdir")
    p.set_defaults(fn=cmd_review_page)
    p = sub.add_parser("lint-script")
    p.add_argument("script")
    p.set_defaults(fn=cmd_lint_script)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except paths.LayoutError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
