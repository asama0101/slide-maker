"""スライド案の収集。`<作業フォルダ>/slides/` の断片を、スライド番号ごとの案にまとめる。

名前の規則は `NN-R1.html`〜`NN-R3.html`（どのページも 2〜3 案。構造の違う案を並べる）。`NN-A.html` は使えない。"""

import re
from pathlib import Path

from . import paths, svgids

_NAME = re.compile(r"^(\d{2})-(R[1-3])\.html$")


def collect(work: Path) -> dict[str, dict[str, str]]:
    """スライド番号 → 案の名前（"R1"〜"R3"）→ 断片。不正な名前や組み合わせは、全件まとめて ValueError。"""
    d = Path(work) / "slides"
    if not d.is_dir():
        raise ValueError(f"{d} がありません（slides/NN-R1.html の形で案を置いてください）")
    # 数字で始まる（先頭の s・S は可）.html は断片のつもりとみなす（_NAME に合わなければ書き間違いか旧形式）。
    # draft-1.html・notes.html などは無視する
    files = sorted(f for f in d.iterdir() if f.suffix.lower() == ".html" and re.match(r"[sS]?\d", f.stem))
    errors: list[str] = []
    type_pages = [f.name for f in files if re.fullmatch(r"\d{2}-A\.html", f.name)]
    for n in type_pages:
        errors.append(f"{n}: 型のページも 2〜3 案（{n[:2]}-R1.html〜）にしてください")
    bad = [f.name for f in files if not _NAME.match(f.name) and f.name not in type_pages]
    if bad:
        errors.append(
            f"断片の名前として読めないファイルがあります: {', '.join(bad)}"
            "（旧形式の名前は使えません。どのページも NN-R1.html〜NN-R3.html。"
            "NN は 2 桁で、-d2・-d3 は付けません）"
        )
    found: dict[str, list[Path]] = {}
    for f in files:
        m = _NAME.match(f.name)
        if m:
            found.setdefault(m.group(1), []).append(f)
    for nn, fs in sorted(found.items()):
        if len(fs) < 2:
            errors.append(f"{nn}: 2〜3 案（{nn}-R1.html〜{nn}-R3.html のうち 2〜3 個）が要ります")
    nums = {int(f[:2]) for f in [*found, *type_pages]}
    missing = [f"{i:02d}" for i in range(1, max(nums, default=0) + 1) if i not in nums]
    if missing:
        errors.append(f"スライド番号が連続していません。足りない番号: {', '.join(missing)}")
    if 0 in nums:
        errors.append("スライド番号は 01 から始めます（00 は使えません）")
    if errors:
        raise ValueError("\n".join(errors))
    if not found:
        raise ValueError(f"{d} に NN-R1.html の形のファイルがありません")
    out: dict[str, dict[str, str]] = {}
    for nn, fs in found.items():
        for f in fs:
            key = _NAME.match(f.name).group(2)
            # 絵（pp-picture）の SVG の id は案ごとに一意にする（別の絵の定義に引かれて、アイコンや矢じりが消えない）
            out.setdefault(nn, {})[key] = svgids.uniquify(paths.read_text(f), f"s{nn}{key.lower()}-")
    return out


_MAIN_CLASS = re.compile(r"""class\s*=\s*["'][^"']*\bpp-(?:chart|table|picture|image)(?![\w-])""")


def _has_main_visual(html: str) -> bool:
    """タグのうち、グラフ・表・絵、またはアイコン以外の画像（写真など）があるか。"""
    for tag in re.findall(r"<[^>]*>", html):
        if not _MAIN_CLASS.search(tag):
            continue
        if re.search(r"""\bdata-role\s*=\s*["']icon["']""", tag) and not re.search(
            r"""class\s*=\s*["'][^"']*\bpp-(?:chart|table|picture)(?![\w-])""", tag
        ):
            continue
        return True
    return False


def main_visual_warnings(cands: dict[str, dict[str, str]], exempt: set[str]) -> list[str]:
    """図・絵・表・グラフが主役でない案を、"NN-Rk: …" の形で返す。表紙・裏表紙など免除の番号は見ない。"""
    return [
        f"{nn}-{key}: 図・絵・表・グラフが主役になっていません"
        for nn, variants in sorted(cands.items())
        if nn not in exempt
        for key, html in variants.items()
        if not _has_main_visual(html)
    ]
