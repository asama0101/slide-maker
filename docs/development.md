# 開発者向けの情報

slide-maker（v1.0.0）の内部構造・コマンド・テストの説明。利用者向けの説明は [README.md](../README.md)。

## 依存関係

`python run.py --data <絶対パス> doctor`（`run.py` は `plugins/slide-maker/` にある。スキルの中では `python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" doctor`。置き場は環境変数 `SLIDE_MAKER_HOME` でも指定でき、そちらが優先される）で、専用の仮想環境の状態を項目ごとの OK/NG で確認できる。

| 区分 | 内容 |
|---|---|
| 必須 | Windows、Python 3.10 以上、Claude Code。`python` が PATH にあること |
| 必須 | **専用の仮想環境**（`<置き場>\venv`。`python-pptx==1.0.2`・`playwright==1.52.0`・`pymupdf==1.28.2`・`lxml==6.1.3`。すべて `==` で固定）。`python run.py --data <絶対パス> setup --yes` で、利用者の承認後に作る。Playwright の chromium（数百 MB）は共有の場所（既定は `%LOCALAPPDATA%\ms-playwright`）に入る |
| 推奨 | BIZ UDPゴシック。未導入だと計測が代替フォントになり、PowerPoint と折り返しがずれることがある |
| 最終確認 | Microsoft PowerPoint（確認用の画像は HTML の撮影で、PPTX の実描画ではない） |

LibreOffice と Playwright MCP は使わない。依存のハッシュ固定は見送っている（Python と CPU の組み合わせが多く、更新の負担が大きいため）。`probe-cache.json`（置き場の下）には `schema_version` を入れている。

## 流れ

成果物は利用者が決めた出力先に置く。

```
<出力先>/
  <成果物名>.pptx
  slide-maker-source/<成果物名>/   元データ: design.md・script.md・slides/・template.json・material/ など
```

1. チャットで入力・保存先・成果物名を受け取り、`init` で作業フォルダを作る。
2. `design.md` → `script.md`（`lint-script`）。人の承認はない。
3. `slides/` に断片を書く。型のページ（表紙・裏表紙・本文の土台・グラフ 6 種・表 2 種）は `NN-A.html`、それ以外は自由設計の `NN-R1.html`〜`NN-R3.html`。
4. `review-page` が `review.html` を作り、Claude が `Artifact` ツールで非公開に公開する（`capabilities` は `review_page.CAPABILITIES`: `db` と `comments`（`composer_only`・`customAnchors`））。利用者が 1 ページごとに案を選び、承認する。コメントは画面の中ではなく、claude.ai の標準のコメント（「このページにコメントする」→「Claude に送信」にチェックして送る）。
5. Claude が `ArtifactData` の `list`（`out_dir`）で `<out_dir>/choices/<NN>.json` に選択を、`ArtifactComments` の `read` でコメントを読む。コメントのあるページは断片だけ直して同じ Artifact を再公開し、スレッドに返信・解決し、承認済みだったページは `status` を `saved` に戻す。`finalize --choices <out_dir>` は全ページ承認済みを確かめて `final.html` を作る（未解決のコメントの確認は、Claude の手順）。
6. `build` が測定 → 検査 → PPTX の書き出し → 再検査。
7. 直しは PowerPoint で行う。構成を大きく変えるときは最初から作り直す。

絵（型に当てはまらない図）は create スキルの 3 章と `references/picture-craft.md`。`<div class="pp-picture" data-alt="…">` の中のインライン SVG で描き、`build` が Chromium で絵の範囲だけを透過・3 倍の PNG にして貼る。部品は `assets/pictures/parts.svg`、見本 5 種は `assets/components/pictures/`、作法は `references/picture-craft.md`。

## 部品

`plugins/slide-maker/assets/components/` に 16 本: `layouts/`（`cover`・`closing`・`text`）、`charts/`（`bar`・`hbar`・`line`・`pie`・`stacked`・`waterfall`）、`tables/`（`options`・`actions`）、`pictures/`（5 種）。デザイン違い（`-d2`・`-d3`）はない。ほかのページは自由設計で、指針は `references/html-rules.md` の「自由設計（R）の指針」。アイコンは `assets/icons/` の 30 個（`references/icons.md`）で、ほかは SVG でその場で描く。型を足したら `components.md`・`patterns.md` も更新し、`tests/test_components.py` を通す。

## ファイルの置き場所

| 場所 | 内容 |
|---|---|
| `.claude-plugin/marketplace.json` | 配布の定義（マーケットプレイス名 `slide-maker`） |
| `plugins/slide-maker/` | `.claude-plugin/plugin.json`、`run.py`、`requirements.txt`、`skills/`（`create`・`template`）、`slide_maker/`（Python）、`references/`、`assets/`（`components/`・`web/`・`icons/`・`template/standard.potx`・`sample/`・`pictures/parts.svg`） |
| `tests/` | 単体・通しのテスト |
| `%TEMP%\slide-maker\<成果物名>-<ハッシュ 8 桁>\` | 確認用の画像など一過性のもの |

## コマンド

普段はスキルが呼ぶ。`python run.py --data <絶対パス> <コマンド>`（`--data` は先頭に置く。`SLIDE_MAKER_HOME` を設定すれば省ける。どちらもなければ終了コード 3）。`<元データ>` は作業フォルダで、`<出力先>/<成果物名>.pptx` のパスを渡しても同じ作業フォルダに解決される（旧配置は終了コード 2）。

| コマンド | 内容 |
|---|---|
| `doctor` / `setup --yes` | 環境の診断 / 仮想環境と chromium の導入（承認後） |
| `init <元データ> --color … [--template …] [--footer …] [--force]` | 作業フォルダを作る |
| `template-import / template-list / template-remove` | 利用者のテンプレートの登録・一覧・削除（使うレイアウトは表紙・本文・裏表紙） |
| `lint-script <script.md>` | 原稿の書式・題・ヘッドメッセージを検査する |
| `review-page <元データ>` | 案を選ぶ Artifact 用の `review.html` を作る（ローカルの画像は data URI に埋め込む。12 MiB まで） |
| `finalize <元データ> --choices <dir>` | 全ページ承認済みの選択結果から `final.html` を作る（`<dir>` は `choices/` の親） |
| `check <final.html>` | 体裁を検査する |
| `build <元データ> [--footer …] [--out …] [--force]` | PPTX を書き出す。出力先に同名の PPTX があれば `--force` がない限り終了コード 4。検査エラーは終了コード 1、入力の不備は 2 |
| `clean <元データ>` | 一時フォルダの確認用の画像を消す |

## 自動検査

`build` が `check_model`（測ったモデル）と `check_pptx`（できた PPTX）で検査する。ルールは `overflow`・`overlap`・`textLost`・`keepout`・`fontMin` と、`outOfSlide`・`shapeKind`・`pptxBounds`・`pptxFontMin`（`references/check-rules.md`）。不正な `data-chart` は `build` が `エラー:` で止める。`lint-script` は原稿の書式と題（20 字以内の名詞句）、ヘッドメッセージの規則、論点の個数を検査する。利用者が書くファイルは UTF-8（BOM 付きも可）。

古い作業フォルダは `base.css`・`theme.css`・`chart-preview.js` が `init` 時の写しなので、プラグイン側の更新を反映するには `init --force` をやり直す。v1.x の作業フォルダ（`answers-*.md`・`-d2` の断片・`NN-R.html` など）は未対応で、`finalize`・`review-page` が旧い名前を挙げて止まる。

## テスト

リポジトリのルートで、専用の仮想環境の Python を使って実行する。ブラウザを使うテストには `slow` マークが付き、`-m "not slow"` で除ける。

    python plugins/slide-maker/run.py --data <置き場> setup --yes
    "<置き場>\venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
    set PYTHONUTF8=1
    set SLIDE_MAKER_HOME=<置き場>
    "<置き場>\venv\Scripts\python.exe" -m pytest
    "<置き場>\venv\Scripts\python.exe" -m ruff check .
    "<置き場>\venv\Scripts\python.exe" -m ruff format --check .
