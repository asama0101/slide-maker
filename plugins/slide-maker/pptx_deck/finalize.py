"""選択結果から最終 HTML（final.html）を作る。"""

import html as _html
from pathlib import Path

from . import candidates, choices, paths

HEAD = (
    '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{title}</title>'
    '<link rel="stylesheet" href="theme.css"><link rel="stylesheet" href="base.css">'
    '<script src="chart-preview.js" defer></script></head><body>'
)


def finalize(work: Path, choices_dir: Path) -> Path:
    """`choices_dir`（choices/ を含むフォルダ）の選択結果から `final.html` を書いて返す。
    承認されていない・案が決まっていない・コメント未反映・選択結果がないスライドがあれば、全件まとめて ValueError。"""
    work = Path(work)
    cands = candidates.collect(work)
    ch = choices.load(choices_dir)
    if not ch:
        raise ValueError("選択結果が空です（Artifact で選んで承認してから取り込んでください）")
    problems: list[str] = []
    picked: dict[str, str] = {}
    for nn in sorted(cands):
        c = ch.get(nn)
        if c is None:
            problems.append(f"S{nn}: 選択結果がありません")
        elif c["status"] != "approved":
            problems.append(f"S{nn}: 承認されていません（状態: {c['status'] or '不明'}）")
        elif not isinstance(c["pick"], str) or c["pick"] not in cands[nn]:
            problems.append(f"S{nn}: 選ばれた案 {c['pick']} が slides/ にありません（候補: {', '.join(cands[nn])}）")
        elif c["comment"]:
            problems.append(f"S{nn}: コメント未反映です: {c['comment']}")
        else:
            picked[nn] = cands[nn][c["pick"]]
    if problems:
        raise ValueError("\n".join(problems))
    body = "\n".join(picked[nn] for nn in sorted(picked))
    out = work / "final.html"
    out.write_text(HEAD.format(title=_html.escape(paths.deck_name(work))) + body + "</body></html>", encoding="utf-8")
    return out
