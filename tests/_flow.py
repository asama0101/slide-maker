"""新しい流れ（choices/*.json → finalize --choices）をテストで通す補助。"""

import json
from pathlib import Path

from slide_maker import candidates, cli


def write_choices(base: Path, picks: dict[str, str]) -> Path:
    """`base/choices/<NN>.json` に承認済みの選択を書き、`base` を返す。"""
    d = Path(base) / "choices"
    d.mkdir(parents=True, exist_ok=True)
    for nn, pick in picks.items():
        data = {"at": "2026-11-08T00:00:00.000Z", "comment": "", "pick": pick, "status": "approved"}
        (d / f"{nn}.json").write_text(json.dumps(data), encoding="utf-8")
    return Path(base)


def finalize_all(work: Path, picks: dict[str, str] | None = None, choices_dir: Path | None = None) -> int:
    """全スライドを承認して finalize する。picks にないスライドは最初の案（R1）を選ぶ。終了コードを返す。"""
    work = Path(work)
    chosen = {nn: (picks or {}).get(nn) or sorted(c)[0] for nn, c in candidates.collect(work).items()}
    base = write_choices(choices_dir or work.parent / f"{work.name}-choices", chosen)
    return cli.main(["finalize", str(work), "--choices", str(base)])


def write_slide(slides: Path, nn: str, html: str, html2: str | None = None) -> None:
    """`slides/NN-R1.html` と `NN-R2.html` を書く（どのページも 2 案が要る）。html2 がなければ同じ内容。"""
    Path(slides).mkdir(parents=True, exist_ok=True)
    for key, body in (("R1", html), ("R2", html if html2 is None else html2)):
        (Path(slides) / f"{nn}-{key}.html").write_text(body, encoding="utf-8")
