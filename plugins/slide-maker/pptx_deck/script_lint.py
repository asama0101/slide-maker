"""原稿（script.md）の書式を検査する。内容の良し悪しは見ない。"""

import re

LAYOUTS = {"cover", "content", "diagram", "table", "chart", "divider", "closing"}
_SLIDE = re.compile(r"^## (S\d{2})(?!\d)\s*(.*)$")
_TOO_MANY = re.compile(r"^## S\d{3,}")
_NEAR_MISS = re.compile(r"^#{2,3}\s*[Ss]\d+")
_FIELD = re.compile(r"^- ([^:：]+)[:：]\s*(.*)$")
_ITEM = re.compile(r"^\s+- (.*)$")

_JUDGE = [
    "すべきだ",
    "べきだ",
    "に限られる",
    "に値する",
    "を左右しない",
    "ではなく",
    "にすぎず",
    "が見込める",
    "できる",
    "が必要だ",
    "必要がある",
    "縮む",
    "減る",
    "増える",
    "高い",
    "低い",
    "切れる",
]
# 「ある」「ない」は、部分一致だと「あるべき姿」「あるいは」まで拾うので、文末のときだけ判断語とみなす
_END_JUDGE = re.compile(r"(ある|ない)。?$")
_CONNECT = ["ため", "だが", "ことで", "ば、", "が、", "ので"]
_BODY_LAYOUTS = {"content", "diagram", "table", "chart"}
_DASH = re.compile("[—―─]")
_SELF = re.compile(r"本ページ|この1枚|この１枚|本スライド")
_TITLE_END = re.compile(
    r"(する|した|される|できる|だ|である|です|ます|ある|ない|べき|れる|なる|か|よう|減る|増える|縮む)$"
)
_TYPES = [
    ("提言", re.compile(r"べきだ|必要がある|が必要だ")),
    ("逆接", re.compile(r"だが|が、")),
    ("条件", re.compile(r"ば、")),
    ("起因", re.compile(r"ではなく")),
    ("評価", re.compile(r"を左右しない|の範囲にあり")),
    ("因果", re.compile(r"ため、|ことで")),
]


def sentence_type(head: str) -> str:
    for name, rx in _TYPES:
        if rx.search(head):
            return name
    return "その他"


def _layout(fields) -> str:
    """layout が空・サブリストのときは文字列でないので、不正な値として空文字にそろえる。"""
    v = fields.get("layout")
    return v if isinstance(v, str) else ""


def _issues(md: str):
    items, cur = [], False
    for line in md.splitlines():
        if line.startswith("## "):
            break
        m = _FIELD.match(line)
        if m:
            cur = m.group(1).strip() == "論点"
            continue
        it = _ITEM.match(line)
        if it and cur:
            items.append(it.group(1).strip())
    return items


def _title_problems(sid, title):
    """題（短い名詞句・20 字以内）。判断は書かない（判断はヘッドメッセージに）。"""
    out = []
    if len(title) > 20:
        out.append(f"{sid}: 題の字数が {len(title)} です（20 字以内の短い名詞句）")
    if re.search(r"[。！？、]", title):
        out.append(f"{sid}: 題に句読点・文末記号は使えません（短い名詞句にする。判断はヘッドメッセージに書く）")
    elif _TITLE_END.search(title):
        out.append(f"{sid}: 題が文の形です（名詞句にする。判断はヘッドメッセージに書く）: {title}")
    return out


def title_notes(md: str) -> list[str]:
    """本文スライドに「題」がないときの案内。エラーではない（ヘッドメッセージはそのまま題の代わりになる）。"""
    slides = parse(md)
    missing = [s["id"] for s in slides if _layout(s["fields"]) in _BODY_LAYOUTS and not s["fields"].get("題")]
    if not missing:
        return []
    return [
        f"案内: 本文スライド {len(missing)} 枚（{', '.join(missing[:6])}{' ほか' if len(missing) > 6 else ''}）"
        "に「題」がありません。"
        "ページ枠は 題（20 字以内の短い名詞句）＋ヘッドメッセージ（判断を言い切る 30〜60 字）の 2 段です。"
        "「- 題: …」を足してください。"
    ]


def _head_problems(sid, head):
    out = []
    n = len(head)
    if not (30 <= n <= 60):
        out.append(f"{sid}: ヘッドメッセージの字数が {n} です（30〜60 字。まず 1 行 36 字幅で書く）")
    if "。" in head.rstrip("。"):
        out.append(f"{sid}: ヘッドメッセージが「A。B」の二段構えです（接続語で 1 文に畳む）")
    if _DASH.search(head):
        out.append(f"{sid}: ヘッドメッセージにダッシュを使わないでください")
    if _SELF.search(head):
        out.append(f"{sid}: ヘッドメッセージに自己言及（本ページ・この1枚）を書かないでください")
    if not (any(j in head for j in _JUDGE) or any(c in head for c in _CONNECT) or _END_JUDGE.search(head)):
        out.append(f"{sid}: ヘッドメッセージに判断語か接続語がありません（題名ではなく、判断を言い切る一文に）")
    return out


def parse(md: str) -> list[dict]:
    slides, cur, field = [], None, None
    for line in md.splitlines():
        m = _SLIDE.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2).strip(), "fields": {}}
            slides.append(cur)
            field = None
            continue
        if cur is None:
            continue
        f = _FIELD.match(line)
        if f:
            field = f.group(1).strip()
            cur["fields"][field] = f.group(2).strip() if f.group(2).strip() else []
            continue
        it = _ITEM.match(line)
        if it and field is not None:
            if not isinstance(cur["fields"][field], list):
                cur["fields"][field] = [cur["fields"][field]]
            cur["fields"][field].append(it.group(1).strip())
    return slides


def exempt_ids(md: str) -> set[str]:
    """図表の主役の警告を免除するスライド番号（layout が cover・closing・divider。S02 なら "02"）。"""
    return {s["id"][1:] for s in parse(md) if _layout(s["fields"]) in {"cover", "closing", "divider"}}


def lint(md: str) -> list[str]:
    slides = parse(md)
    if not slides:
        return ["スライド（## S01 …）がありません"]
    out = []
    for (
        line
    ) in md.splitlines():  # 見出しの書き損じ（## S1・### S02・##S02・## s02）は、前のスライドに混ざるので先に知らせる
        if _TOO_MANY.match(line):
            out.append(f"スライドは 99 枚までです（S100 以降は扱えません）: {line.strip()!r}")
        elif _NEAR_MISS.match(line) and not _SLIDE.match(line):
            out.append(f"見出しの書式が不正です: {line.strip()!r}（`## S01 名前` の形にしてください）")
    for i, s in enumerate(slides, start=1):
        sid, f = s["id"], s["fields"]
        if sid != f"S{i:02d}":
            out.append(f"{sid}: 番号が連番ではありません（{i} 番目は S{i:02d}）")
        layout = _layout(f)
        if layout not in LAYOUTS:
            out.append(f"{sid}: layout が不正です: {layout!r}（{', '.join(sorted(LAYOUTS))}）")
        if i == 1 and layout != "cover":
            out.append(f"{sid}: 最初のスライドは表紙（layout: cover）にしてください")
        if layout == "divider":
            continue  # 区切りは題だけ（任意）。ヘッドメッセージ・章名・本文は要らない
        if not f.get("ヘッドメッセージ"):
            out.append(f"{sid}: ヘッドメッセージがありません")
        elif not isinstance(
            f["ヘッドメッセージ"], str
        ):  # サブリスト書きは文字列でないので、字数などの検査はせず書き方だけ知らせる
            out.append(f"{sid}: ヘッドメッセージは 1 行で書いてください（リストにしない）")
        elif layout in _BODY_LAYOUTS:
            out.extend(_head_problems(sid, f["ヘッドメッセージ"]))
            if isinstance(f.get("題"), str) and f["題"]:
                out.extend(_title_problems(sid, f["題"]))
        if layout not in ("cover", "closing") and not f.get("章名"):
            out.append(f"{sid}: 章名（そのスライドが答える問い）がありません")
        if layout not in ("cover", "closing") and not (f.get("本文") or f.get("図表")):
            out.append(f"{sid}: 本文か図表のどちらかが必要です")
        if layout in ("diagram", "table", "chart") and not f.get("図表"):
            out.append(f"{sid}: layout が {layout} のときは図表（型と理由）が必要です")
        if layout in _BODY_LAYOUTS:
            for name in ("主役の図表", "読み手にさせたいこと"):
                if not f.get(name):
                    out.append(f"{sid}: {name}がありません")
    issues = _issues(md)
    if issues and not (3 <= len(issues) <= 6):
        out.append(f"論点は 3〜6 個にしてください（今は {len(issues)} 個）")
    run, prev = 0, None
    for s in slides:
        h = s["fields"].get("ヘッドメッセージ")
        if _layout(s["fields"]) not in _BODY_LAYOUTS or not isinstance(h, str):
            run, prev = 0, None
            continue
        t = sentence_type(h)
        run = run + 1 if t == prev and t != "その他" else 1
        prev = t
        if run == 3:
            out.append(f"{s['id']}: 隣り合う 3 枚のヘッドメッセージが同じ文型（{t}）です。文型を散らしてください")
    return out
