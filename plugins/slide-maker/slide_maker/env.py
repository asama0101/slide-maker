"""実行に使う Python（専用 venv の Python）の選択と、導入。標準ライブラリのみ。"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path

from . import paths

# pip 名 → 要求する版（すべて == で固定）。requirements.txt と同じ内容（テストで一致を確かめる）
MIN_PYTHON = (3, 10)
REQUIREMENTS = {"python-pptx": "==1.0.2", "playwright": "==1.52.0", "pymupdf": "==1.28.2", "lxml": "==6.1.3"}

_PROBE = (
    r"""
import json, os, sys
import importlib.metadata as m
out = {"python": list(sys.version_info[:2]), "versions": {}, "chromium": False}
for pkg in ("python-pptx", "playwright", "pymupdf", "lxml"):
    try:
        out["versions"][pkg] = m.version(pkg)
    except m.PackageNotFoundError:
        out["versions"][pkg] = None
if out["versions"]["playwright"] == "%PW%":      """
    r"""# 版が違えばこの Python は使えないので、chromium の確認（Playwright の起動）は飛ばす
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        out["chromium"] = os.path.exists(p.chromium.executable_path)
        p.stop()
    except Exception:
        pass
print(json.dumps(out))
""".replace("%PW%", REQUIREMENTS["playwright"][2:])
)

# site-packages と chromium の置き場の更新時刻。
# import せず stat だけなので軽い（pip の更新・chromium の入れ替えを検知する）
_STAMP = (
    r"""
import json, os, site, sysconfig
def m(p):
    try:
        return os.stat(p).st_mtime_ns
    except OSError:
        return None
pure = sysconfig.get_paths()["purelib"]
try:
    user = site.getusersitepackages()
except Exception:
    user = ""
browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or """
    r"""os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
print(json.dumps([m(pure), m(os.path.join(pure, "playwright")), m(user), m(browsers)]))
"""
)


def probe(python: Path) -> dict:
    """指定した Python に、必要なものがどう入っているか。動かない Python は、すべて未導入として返す。"""
    empty = {"python": [0, 0], "versions": {k: None for k in REQUIREMENTS}, "chromium": False}
    try:
        r = subprocess.run(  # noqa: S603  # 引数は配列、実行ファイルは自分で解決した Python
            [str(python), "-c", _PROBE], capture_output=True, text=True, timeout=120
        )
        return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else empty
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return empty


def _stamp(python: Path) -> list | None:
    """調べる Python の site-packages・chromium の置き場の更新時刻。取れなければ None（キャッシュしない）。"""
    try:
        r = subprocess.run(  # noqa: S603  # 引数は配列、実行ファイルは自分で解決した Python
            [str(python), "-c", _STAMP], capture_output=True, text=True, timeout=30
        )
        out = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    return out if isinstance(out, list) else None


def missing(info: dict) -> list[str]:
    out = []
    if tuple(info.get("python", [0, 0])) < MIN_PYTHON:
        out.append("Python 3.10 以上が必要です")
    for pkg, spec in REQUIREMENTS.items():
        ver = info["versions"].get(pkg)
        if ver is None:
            out.append(f"{pkg} が未導入です")
        elif ver != spec[2:]:
            out.append(f"{pkg} {ver}（要 {spec}）")
    if not info.get("chromium"):
        out.append("Playwright の chromium が使えません")
    return out


@dataclass
class Selection:
    path: Path | None  # 実行に使う専用 venv の Python。使えないときは None
    missing: list[str]  # 専用 venv が使えない理由（path があれば空）


# 調査結果のキャッシュ。検査項目（要求する版と調査のコード）が変わったら自動で無効になる
# ファイル形式の版。形式を変えたら上げる。ない・違う版のキャッシュは作り直せるので、捨てて調べ直す
_SCHEMA_VERSION = 1
_CACHE_VERSION = hashlib.sha256((json.dumps(REQUIREMENTS, sort_keys=True) + _PROBE).encode("utf-8")).hexdigest()[:16]


def _cache_file() -> Path | None:
    try:
        return paths.home_dir() / "probe-cache.json"
    except RuntimeError:
        return None


def _load_cache() -> dict:
    f = _cache_file()
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f else None
    except (OSError, ValueError):
        return {}
    if (
        isinstance(data, dict)
        and data.get("schema_version") == _SCHEMA_VERSION
        and data.get("version") == _CACHE_VERSION
        and isinstance(data.get("entries"), dict)
    ):
        return data["entries"]
    return {}


def _save_cache(entries: dict) -> None:
    f = _cache_file()
    if f is None:
        return
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=f.parent, prefix="probe-cache-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"schema_version": _SCHEMA_VERSION, "version": _CACHE_VERSION, "entries": entries}, fh)
            Path(tmp).replace(f)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError:
        pass  # キャッシュに書けなくても、実行は止めない


def _probe_cached(python: Path, refresh: bool = False) -> dict:
    """probe の結果を、インタープリタのパス・更新時刻と site-packages の状態（_stamp）をキーにキャッシュする。
    そろっている（問題なし）結果だけを残し、失敗や不足は残さない（あとから導入されることがあるため、毎回調べ直す）。
    refresh=True は必ず調べ直してキャッシュを更新する。"""
    try:
        mtime = python.stat().st_mtime_ns
    except OSError:
        return probe(python)  # 存在しない Python は、そのまま調べる（キャッシュしない）
    key = str(python)
    stamp = _stamp(python)  # None なら状態が分からないので、キャッシュを使わず残さない
    entries = _load_cache()
    hit = entries.get(key)
    if (
        not refresh
        and stamp is not None
        and isinstance(hit, dict)
        and hit.get("mtime") == mtime
        and hit.get("stamp") == stamp
        and isinstance(hit.get("info"), dict)
    ):
        return hit["info"]
    info = probe(python)
    if not missing(info) and stamp is not None:
        entries[key] = {"mtime": mtime, "stamp": stamp, "info": info}
        _save_cache(entries)
    elif key in entries:
        del entries[key]
        _save_cache(entries)
    return info


def select_python(refresh: bool = False) -> Selection:
    """専用 venv の Python が、必要なものを固定した版でそろえていればそれを返す。
    refresh=True（doctor）は、キャッシュを使わず実際に調べ直す。"""
    vpy = paths.venv_python()
    if not vpy.exists():
        return Selection(None, ["仮想環境がありません"])
    miss = missing(_probe_cached(vpy, refresh))
    return Selection(None if miss else vpy, miss)


def base_python_problems() -> list[str]:
    """venv の作成元（run.py を動かしている Python）で、venv を作れない理由。"""
    out = []
    if tuple(sys.version_info[:2]) < MIN_PYTHON:
        out.append(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 以上が必要です（今は {sys.version_info[0]}.{sys.version_info[1]}）"
        )
    for mod in ("venv", "ensurepip"):
        if importlib.util.find_spec(mod) is None:
            out.append(f"Python 標準ライブラリの {mod} が使えません（venv を作れません）")
    return out


def venv_healthy() -> bool:
    """venv の python.exe が実際に動くか（基底の Python が消えた venv は、ファイルがあっても動かない）。"""
    try:
        r = subprocess.run(  # noqa: S603  # 引数は配列、実行ファイルは専用 venv の Python
            [str(paths.venv_python()), "-c", "pass"], capture_output=True, timeout=60
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def diagnosis(sel: Selection) -> list[str]:
    """doctor が出す、項目ごとの OK/NG と対処法。何も変更しない。"""
    out = []
    base = base_python_problems()
    if base:
        out += [f"[NG] 作成元の Python: {p}" for p in base]
        want = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
        out.append(f"  → Python {want} 以上（venv と ensurepip 付き）を入れて、そちらで run.py を実行する")
    else:
        out.append(f"[OK] 作成元の Python {sys.version_info[0]}.{sys.version_info[1]}")
    fix = "  → 利用者の承認後に `setup --yes`（専用 venv を作って導入）を実行する"
    if not paths.venv_python().exists():
        out += ["[NG] 仮想環境: ありません", fix]
    elif not venv_healthy():
        out += ["[NG] 仮想環境: 壊れています（基底の Python が消えた可能性）", fix + "。venv は作り直す"]
    elif sel.missing:
        out += [f"[NG] 仮想環境: {m}" for m in sel.missing] + [fix]
    else:
        out.append("[OK] 仮想環境・ライブラリ・chromium")
    return out


def _install(py: str) -> int:
    req = str(paths.SKILL_DIR / "requirements.txt")
    for cmd in ([py, "-m", "pip", "install", "-r", req], [py, "-m", "playwright", "install", "chromium"]):
        rc = subprocess.call(cmd)  # noqa: S603  # 引数は配列、実行ファイルは専用 venv の Python
        if rc != 0:
            print(f"失敗: {' '.join(cmd)}", file=sys.stderr)
            return rc
    return 0


def setup(yes: bool) -> int:
    problems = base_python_problems()
    if problems:
        print("仮想環境を作れません: " + "、".join(problems))
        print(
            f"作成元の Python は {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 以上で、venv と ensurepip が使えるものにしてください。"
        )
        return 3
    target = paths.venv_dir()
    if not yes:
        print(f"仮想環境が必要です。作成先: {target}")
        print("作成内容: python -m venv ＋ requirements.txt の導入 ＋ Playwright の chromium（数百 MB）。")
        print(
            "利用者の承認を得てから `setup --yes` を実行してください。"
            "chromium は Playwright の共有の場所（既定は %LOCALAPPDATA%\\ms-playwright）に入ります。"
        )
        return 3
    target.parent.mkdir(parents=True, exist_ok=True)
    if not paths.venv_python().exists():
        venv.EnvBuilder(with_pip=True).create(target)
    elif not venv_healthy():  # 動かない venv は作り直す（承認済みの置き場の venv だけ）
        print(f"仮想環境が壊れています。作り直します: {target}")
        venv.EnvBuilder(with_pip=True, clear=True).create(target)
    rc = _install(str(paths.venv_python()))
    if rc == 0:
        print("環境を作成しました:", target)
    return rc
