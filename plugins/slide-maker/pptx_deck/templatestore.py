"""利用者のテンプレートの置き場（<置き場>/templates/<名前>.potx|.pptx）。

プラグインを更新しても残る場所に、名前を付けて 1 つずつ置く。作成済みの成果物は
作業フォルダの _template/ にコピーを持つので、ここを消しても影響しない。
"""

import os
import shutil
import tempfile
from pathlib import Path

from . import paths, template

SUFFIXES = (".potx", ".pptx")


def check_name(name: str) -> str:
    """ファイル名に使える名前か。使えなければ ValueError。"""
    if problem := paths.filename_problem(name):
        raise ValueError(f"テンプレートの名前に使えません（{problem}）: {name!r}")
    return name


def _find(name: str) -> Path | None:
    return next((p for ext in SUFFIXES if (p := paths.templates_dir() / f"{name}{ext}").is_file()), None)


def import_template(src, name: str | None = None, force: bool = False) -> dict:
    """src を置き場へコピーする。使えないファイルは何も置かず ValueError、同じ名前があれば FileExistsError。"""
    src = Path(src)
    if src.suffix.lower() not in SUFFIXES:
        raise ValueError(f"テンプレートは .potx か .pptx のファイルを指定してください: {src}")
    name = check_name(name if name is not None else src.stem)
    template.analyze(src)  # 16:9・本文のレイアウトなど、使えるかをここで確かめる（失敗は ValueError）
    old = _find(name)
    if old is not None and not force:
        raise FileExistsError(f"同じ名前のテンプレートがあります: {name}（置き換えるには --force）")
    dst_dir = paths.templates_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{name}{src.suffix.lower()}"
    fd, tmp = tempfile.mkstemp(dir=dst_dir, prefix="import-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out, src.open("rb") as f:
            shutil.copyfileobj(f, out)
        Path(tmp).replace(dst)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    if old is not None and old != dst:
        old.unlink()  # 形式が変わったとき、同じ名前が 2 つ残らないようにする
    return {"name": name, "path": str(dst), "format": dst.suffix}


def list_templates() -> list[dict]:
    d = paths.templates_dir()
    if not d.is_dir():
        return []
    items = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES]
    return [{"name": p.stem, "path": str(p), "format": p.suffix.lower()} for p in sorted(items, key=lambda p: p.stem)]


def remove_template(name: str) -> dict:
    check_name(name)
    p = _find(name)
    if p is None:
        raise ValueError(f"テンプレートが見つかりません: {name}")
    p.unlink()
    return {"name": name, "removed": str(p)}
