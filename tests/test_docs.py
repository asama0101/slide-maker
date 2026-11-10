"""文書（SKILL.md・references・README・plugin.json・requirements.txt）の整合を検査する。"""

# ruff: noqa: S101  # pytest の assert
import json
import re

import pytest

from tests._paths import PKG, REPO

SKILL_NAMES = ("create", "doctor", "template")
SKILL_FILES = sorted((PKG / "skills").rglob("SKILL.md"))
REFERENCE_FILES = sorted((PKG / "references").glob("*.md"))
DOC_FILES = SKILL_FILES + REFERENCE_FILES  # run.py の呼び出し・コマンド名を検査する文書
ALL_MD = sorted(PKG.rglob("*.md"))
REQ_LINES = [x.strip() for x in (PKG / "requirements.txt").read_text(encoding="utf-8").splitlines() if x.strip()]


def read(p):
    return p.read_text(encoding="utf-8")


def rel(p):
    return p.relative_to(PKG).as_posix()


def skill_text(name):
    return read(PKG / "skills" / name / "SKILL.md")


def test_スキルが揃っている():
    assert sorted(f.parent.name for f in SKILL_FILES) == sorted(SKILL_NAMES)


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_スキルの_frontmatter_はスキル名と一致する(name):
    text = skill_text(name)
    m = re.match(r"^---\nname: (.+)\ndescription: (.+)\n(?:compatibility: .+\n)?(?:allowed-tools: .+\n)?---\n", text)
    assert m, f"{name}: frontmatter が読めない"
    assert m.group(1).strip() == name


_RUN_PY_TOOL = 'Bash(python "${CLAUDE_PLUGIN_ROOT}/run.py" *)'
_ARTIFACT_SKILLS = ("create",)  # 案の選択に Artifact を使うスキル
_FRONTEND_DESIGN_TOOL = "Skill(frontend-design:frontend-design)"  # 自由設計の案を考えるときに呼ぶスキル（create だけ）


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_allowed_tools_は_run_py_の呼び出しと_artifact_だけに絞る(name):
    """`Bash(python *)` のような広い許可は書かない。Artifact を使うスキルだけ Artifact・ArtifactData・
    ArtifactComments を許す。"""
    head = skill_text(name).split("\n---\n", 1)[0]
    m = re.search(r"^allowed-tools: '(.+)'$", head, re.M)
    assert m, f"{name}: allowed-tools がない"
    want = [
        _RUN_PY_TOOL,
        *(["Artifact", "ArtifactData", "ArtifactComments"] if name in _ARTIFACT_SKILLS else []),
        *([_FRONTEND_DESIGN_TOOL] if name == "create" else []),
    ]
    assert m.group(1).split(", ") == want


@pytest.mark.parametrize("key", ["name", "version", "description", "license", "repository", "keywords"])
def test_plugin_json_に推奨項目がある(key):
    m = json.loads(read(PKG / ".claude-plugin" / "plugin.json"))
    assert m.get(key), key


def test_plugin_json_の_author_に名前がある():
    m = json.loads(read(PKG / ".claude-plugin" / "plugin.json"))
    assert m["author"]["name"]


@pytest.mark.parametrize("f", SKILL_FILES, ids=lambda f: f.parent.name)
def test_スキルにパスの直書きがなく_プラグインルート変数を使う(f):
    t = read(f)
    assert "C:/Users" not in t
    assert "${CLAUDE_SKILL_DIR}" not in t
    assert "${CLAUDE_PLUGIN_ROOT}" in t


@pytest.mark.parametrize("f", [REPO / "README.md", *ALL_MD], ids=lambda f: f.name if f.name == "README.md" else rel(f))
def test_libreoffice_は依存として書かず_使わないと書く(f):
    for line in read(f).splitlines():
        if re.search(r"LibreOffice|soffice", line):
            assert re.search(r"使わ|使用しな|不要|廃止", line), f"{f}: {line}"


@pytest.mark.parametrize("f", ALL_MD, ids=rel)
def test_参照文書に旧い変数や_pngs_がない(f):
    t = read(f)
    assert "${CLAUDE_SKILL_DIR}" not in t
    assert "pngs" not in t


@pytest.mark.parametrize("f", SKILL_FILES, ids=lambda f: f.parent.name)
def test_スキルのパスはプラグインルート基準で実在する(f):
    """相対リンク（references/…）は使わない。${CLAUDE_PLUGIN_ROOT}/ の後ろは実在する。"""
    t = read(f)
    assert not re.search(r"\]\((references|assets)/", t), "相対リンク"
    assert not re.search(r"`(references|assets)/[A-Za-z0-9_]", t), "地の文の相対パス"
    missing = []
    for m in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}/((?:run\.py|references/|assets/)[A-Za-z0-9_./-]*)", t):
        r = m.group(1)
        if "<" not in r and not (PKG / r.rstrip("/")).exists():
            missing.append(r)
    assert missing == []


def _known_commands():
    cli_src = read(PKG / "pptx_deck" / "cli.py")
    return set(re.findall(r'sub\.add_parser\(\s*"([a-z-]+)"', cli_src)) | {"setup"}  # setup は run.py が直接処理する


@pytest.mark.parametrize("f", DOC_FILES, ids=rel)
def test_文書に書かれたコマンドは_cli_に実在する(f):
    """`run.py" <コマンド>` と書かれたコマンド名は、cli.py の add_parser にある。"""
    known = _known_commands()
    used = re.findall(r'run\.py"(?: --data "\$\{CLAUDE_PLUGIN_DATA\}")? ([a-z][a-z-]*)', read(f))
    assert [c for c in used if c not in known] == []


# v2 で削除したコマンド（`history`・`draft` は普通の語と紛れるので、上の run.py の形の検査に任せる）
_REMOVED_V2 = (
    "variants",
    "apply-edits",
    "review-final",
    "start-page",
    "intake",
    "set-color",
    "set-font-size",
    "output-format",
    "reopen",
    "review-plan",
    "export-html",
    "review-picture",
    "picture-status",
    "template-map",
)


@pytest.mark.parametrize("f", DOC_FILES, ids=rel)
def test_文書に削除したコマンドの名前が残っていない(f):
    t = read(f)
    assert [c for c in _REMOVED_V2 if re.search(rf"(?<![\w-]){re.escape(c)}(?![\w-])", t)] == []


@pytest.mark.parametrize(
    "name",
    ["review-page", "finalize", "build"],
)
def test_主要コマンドが_cli_に登録されている(name):
    assert name in _known_commands()


@pytest.mark.parametrize("f", DOC_FILES, ids=rel)
def test_run_py_の呼び出しはすべて_data_を付ける(f):
    """Bash の環境変数には入らないので、本文の ${...} で渡す。
    frontmatter の allowed-tools（許可の書式）は呼び出しではない。"""
    t = read(f).split("\n---\n", 1)[-1]
    n_all = len(re.findall(r'run\.py"', t))
    n_ok = len(re.findall(r'run\.py" --data "\$\{CLAUDE_PLUGIN_DATA\}"', t))
    assert n_all == n_ok, f"{f.name}: --data のない run.py の呼び出し"


def test_主要コマンドは_run_py_の形で文書に書かれている():
    used = set()
    for f in DOC_FILES:
        used |= set(re.findall(r'run\.py" --data "\$\{CLAUDE_PLUGIN_DATA\}" ([a-z][a-z-]*)', read(f)))
    want = {"doctor", "setup", "init", "template-list", "lint-script", "review-page", "finalize", "build", "clean"}
    assert want <= used, want - used


@pytest.mark.parametrize("f", DOC_FILES, ids=rel)
def test_システムの_python_に入れる経路が書かれていない(f):
    """v2 は専用の仮想環境だけ。システムの Python への導入（`setup --system`）とその判定を書かない。"""
    words = ("--system", "PPTX_DECK_NO_SYSTEM", "python.kind", r"LOCALAPPDATA%\pptx-deck\venv")
    t = read(f)
    assert [w for w in words if w in t] == []


def test_requirements_txt_に依存が書かれている():
    assert REQ_LINES


@pytest.mark.parametrize("line", REQ_LINES, ids=lambda s: s.split("==")[0])
def test_requirements_は_固定の版で書かれている(line):
    assert re.match(r"^[A-Za-z0-9_.-]+==[0-9][A-Za-z0-9_.]*$", line)


@pytest.mark.parametrize(
    "word",
    ["pp-picture", "NN-R1.html", "review-page", "コメント", "PowerPoint で直せない", "xx"],
)
def test_create_に絵を描いて見せてコメントで直す手順の語が書いてある(word):
    assert word in skill_text("create")


@pytest.mark.parametrize("word", ["NW 構成図", "トラフィックフロー", "障害動作", "自己紹介", "marker", "viewBox"])
def test_picture_craft_に絵の作法の語が書いてある(word):
    assert word in read(PKG / "references" / "picture-craft.md")


def test_create_は_picture_craft_を指し_readme_は図の依頼に触れる():
    assert "picture-craft.md" in skill_text("create")
    assert "図にして" in read(REPO / "README.md")


def test_create_は_init_から_build_の順に案内する():
    t = skill_text("create").split("\n---\n", 1)[-1]  # frontmatter の allowed-tools は数えない
    words = ('init "', "input.md", "lint-script", "review-page", "ArtifactData", 'finalize "', 'build "')
    pos = [t.find(w) for w in words]
    assert all(p >= 0 for p in pos), pos
    assert pos == sorted(pos)


@pytest.mark.parametrize(
    "word",
    [
        "review-page",
        "finalize",
        "--choices",
        "ArtifactData",
        "out_dir",
        "capabilities",
        '{"db": {}, "comments": {"composer_only": true, "customAnchors": true}}',
    ],
)
def test_create_に_artifact_での選択の受け取りが書いてある(word):
    assert word in skill_text("create")


def test_create_は最初の公開の前に非公開の_artifact_に載ることを伝える():
    assert re.search(r"最初に公開する前に 1 回.*非公開（作成者のみ閲覧可）の Artifact", skill_text("create"))


def test_create_はコメントで直したページの承認を_pick_を残して戻す():
    t = skill_text("create")
    assert '{"status": "saved"}' in t
    assert '{"comment": "", "status": "saved"}' not in t  # コメントはページに持たない
    assert "if_version" in t
    assert "`pick` は残す" in t


@pytest.mark.parametrize("word", ["ArtifactComments", "Claude に送信", "#pg-", "スライド NN", "reply", "resolve"])
def test_create_は標準のコメントを読み_返信して解決する(word):
    assert word in skill_text("create")


def test_create_は_finalize_の前に未解決のコメントがないことを確かめる():
    t = skill_text("create")
    line = next(x for x in t.splitlines() if x.startswith("`finalize` は未解決のコメントを知らない"))
    assert "ArtifactComments" in line
    assert "未解決" in line


@pytest.mark.parametrize("f", [REPO / "README.md", PKG / "references" / "review-flow.md"], ids=lambda f: f.name)
def test_コメントは_claude_に送信_にチェックを入れて送ると書いてある(f):
    t = read(f)
    assert "このページにコメントする" in t
    assert "「Claude に送信」にチェック" in t
    assert "「保存」" not in t  # 旧ページのボタン


def test_review_flow_は_capabilities_とスレッドの対応と_comment_が常に空であることを書く():
    t = read(PKG / "references" / "review-flow.md")
    assert '{"db": {}, "comments": {"composer_only": true, "customAnchors": true}}' in t
    assert "#pg-NN" in t
    assert "常に空" in t
    assert "resolve" in t


def _section_5_2():
    t = skill_text("create")
    return t[t.index("### 5.2 非公開の確認") : t.index("## 6. PPTX")]


def test_create_は公開の結果の_readable_by_only_you_を根拠に非公開を確かめる():
    s = _section_5_2()
    assert "readable by only you" in s
    # 共有後も出る文は、根拠にしない
    assert "This artifact is private" in s
    assert re.search(r"This artifact is private`? は、共有後も出るので根拠にしない", s)


def test_create_は非公開でないとき選択を読まず_finalize_と_build_も行わない():
    s = _section_5_2()
    assert "読み取りと書き込み" in s
    assert "`finalize`・`build`" in s
    assert "実行しない" in s
    # 読み取れない・文言が違うときも、非公開でないものとして扱う（安全側）
    assert "読み取れない" in s
    assert "安全側" in s


def test_create_は公開_再公開_読む直前のすべてで非公開を確かめる():
    t = skill_text("create")
    sec5 = t[t.index("## 5. 案の選択（Artifact）") : t.index("### 5.2 非公開の確認")]
    # 初回の公開・読む直前の再公開・コメント後の再公開の 3 か所が 5.2 を指す
    assert sec5.count("5.2") >= 3
    assert "読む前に非公開を確かめ直す" in sec5


def test_非公開の確認が_review_flow_readme_にも書いてある():
    assert "readable by only you" in read(PKG / "references" / "review-flow.md")
    assert "非公開かを確かめ" in read(REPO / "README.md")


def _free_design_item():
    t = skill_text("create")
    return next(x for x in t.splitlines() if x.startswith("- **全ページ（表紙・裏表紙も）で 2〜3 案**"))


def test_create_は自由設計の案を考えるとき_frontend_design_スキルを呼ぶ():
    item = _free_design_item()
    assert "frontend-design:frontend-design" in item
    # 使うのは観点だけ。色・フォント・装飾は pp-* と検査の制約に従う
    assert "観点だけ" in item
    # スキルが入っていなくても止まらない
    assert "なければ" in item


def test_html_rules_に_frontend_design_の使う観点と使わない観点が書いてある():
    t = read(PKG / "references" / "html-rules.md")
    sec = t[t.index("## 自由設計（R）の指針") :]
    assert "frontend-design" in sec
    assert "使う観点" in sec
    assert "使わない" in sec
    # PPTX に出せない装飾の例を挙げている
    for word in ("グラデーション", "影", "アニメーション", "Web フォント"):
        assert word in sec, word


def test_create_は_build_の終了コード4で_force_か_out_を選ばせる():
    line = next(x for x in skill_text("create").splitlines() if "終了コード 4" in x)
    assert "--force" in line
    assert "--out" in line


def test_スキルと_README_に旧配置の_source_スラッシュ_の説明が残っていない():
    for f in [*ALL_MD, REPO / "README.md"]:
        t = read(f)
        assert "<名前>/source/" not in t, f
        assert not re.search(r"(?<![\w-])source/(slides|script|design|final)", t), f


def test_成果物の用語が統一されている():
    old = "".join(["作", "品"])
    targets = [f for ext in ("py", "md", "html", "json") for f in PKG.rglob(f"*.{ext}") if "__pycache__" not in f.parts]
    targets += [
        REPO / "CLAUDE.md",
        REPO / "README.md",
        REPO / ".claude-plugin" / "marketplace.json",
        *sorted((REPO / "docs").glob("*.md")),
        *sorted((REPO / "tests").glob("*.py")),
    ]
    offenders = [f.relative_to(REPO).as_posix() for f in targets if f.exists() and old in read(f)]
    assert not offenders, offenders


def test_部品の_html_に旧配置の_source_スラッシュ_の説明が残っていない():
    pat = r"(?<![\w-])source/(slides|script|design|final)"
    offenders = [
        f.relative_to(REPO).as_posix()
        for f in (PKG / "assets" / "components").rglob("*.html")
        if re.search(pat, read(f))
    ]
    assert not offenders, offenders


@pytest.mark.parametrize(
    "f", [REPO / "README.md", *DOC_FILES], ids=lambda f: f.name if f.name == "README.md" else rel(f)
)
def test_removed_names(f):
    """デザイン自由化で廃止した `init --color`・プリセット・`NN-A.html` が文書に残っていない。"""
    t = read(f)
    assert "--color" not in t
    assert "NN-A.html" not in t
    assert not re.search(r"1 枚に 1 点|1 枚 1 点|1 スライドに 1 点", t.replace("**", ""))
    assert "自由設計｜" not in t
    assert not re.search(r"navy|`green`|`gray`", t)
