# 調査結果: 複雑な個所と機能要件

実装を必要最低限にそぎ落とすための調査（2026-11-08、v1.4.3 時点）。

## 規模

| 領域 | 規模 |
|---|---|
| Python 本体 | 31 モジュール、約 7,300 行。関数 310 個、`except` 62 個（`cli.py` だけで 25 個） |
| テスト | 63 ファイル、約 9,900 行。本体より多い |
| 部品の見本（`assets/components`） | 152 ファイル、約 1.1MB（51 型。ほとんどが 3 デザイン） |
| スキル | 6 本、計 63KB。`create/SKILL.md` だけで 35KB（1 行が約 180 字） |
| references | 8 本、計 74KB |
| CLI | サブコマンド 28 個。終了コード 2 を返す箇所が 26、終了コード 4 を返す箇所が 6 |
| 履歴 | 30 コミットのうち約 10 件が「レビュー・監査の指摘を直す」 |

## 複雑な個所

規模の大きい順。

1. **レビュー画面と編集の往復**（`variants.py` 1,161 行、`reviewext.py` 439 行、`fragedit.py` 557 行。合計は本体の約 3 割）
   - `_page` は 171 行の 1 関数。
   - 次の機能が積み重なっている。
     - 部位のバッジとコメント
     - 編集モードと「リセット」ボタン
     - 「承認」「全部承認」「要修正」と、要修正の自動付与（`data-auto`）
     - 警告表示（`.rv-warn`）
   - 画面での編集は、`- 編集: {json}` を介して断片へ「文字列の切り貼り」で戻す。`before` と現在の文字の照合や `skipped` の扱いまである。
   - 回答 md は、回の順に後勝ちで上書きする仕組み（`answers-N.md`、`answers-final.md`、`round-N-notes.md`）。
   - テストも多い: `test_review_edit` 834 行、`test_review_page` 396 行、`test_review_approval` 379 行。
2. **設定の状態管理**（配色・文字サイズ・出力形式）
   - 設定は、画面と回答、`finalize` を通って反映される。ほかに `set-color`、`set-font-size`、`output-format` がある。
   - 状態が `template.json` の `answers_color` と `answers_color_from` にある。「同じファイルの同じ値は再適用しない」「PPTX があれば警告のみ」といった例外規則が付いている。
3. **スライド案の量**
   - 1 ページで 型 A/B/C + 自由設計 R の最大 4 案を作り、型を選んだ後にデザイン 1〜3 を選ぶ。
   - 部品は 51 型 × 最大 3 デザインで 147 本ある。
   - `patterns.md` と `components.md` が、これを選ぶ表。
4. **環境の準備**（`run.py`、`env.py`、`setup`、`doctor`）
   - システムの Python と専用 venv の 2 択がある。
   - `--data` と `PPTX_DECK_HOME`、`PPTX_DECK_NO_SYSTEM`、`probe-cache.json`、`requirements.txt` の完全一致の判定が絡む。
5. **作り直し時の保護**
   - 保護の仕組み:
     - PPTX の指紋（`build.json`）
     - `modified` / `unrecorded` / `missing`
     - `--force` / `--out`
     - 派生ファイルの削除
     - 未反映の編集がある間は 4 コマンドを止める仕組み
     - `intake` の衝突
     - `history`
   - `cmd_build` は 88 行で、保護のためのエラー分岐が 6 つある。
6. **検査**（`check.py` の `check_model`）
   - 240 行、分岐 91 の 1 関数。検査ルールはエラー 9 種と警告 7 種。
   - 同じ検査を、測ったモデルと出力後の PPTX の両方にかけている。
7. **テンプレート**
   - `template.py` 537 行、`templatestore.py`、`template-map`、`template-import` / `list` / `remove`、専用スキル `/slide-maker:template`。
   - 表紙・章扉・目次・型ごとの専用レイアウトを名前で推定する。
8. **絵（`pp-picture`）**
   - `picture_plan.py` 335 行、`draft.py`、`history.py`、`svgids.py`。
   - `diagram` スキル 11KB と `picture-craft.md` 10KB、見本 5 本。
9. **文章の規則**
   - `head-rules.md`、`script_lint.py`（213 行）、設計図と原稿の 2 段階。
   - 5.1 の自己確認には人が見る項目が 5 つある。
   - 任意の `review-plan`（スキルと `plan_review.py`）もある。
10. **スキルの手順書の重複**
    - 「100 秒ずつ 18 回待つ」ループが `create` の中に 2 回あり、`revise` でも参照されている。
    - `create` の 1 項目に、条件分岐が十数個入っている。代表は 3-7 の「`finalize` のあと」の文。
11. **出力形式が 2 系統**
    - `htmlexport.py` が HTML 出力と PPTX 出力の両方を持つ。
12. **その他**
    - `部品見本.html` は生成元がない。
    - CLAUDE.md と README と SKILL.md に同じ説明が散らばっている。

## 機能要件（推測。要確認）

**中核（これがなければ意味がない）**

1. 素材（テーマ・メモ・原稿）から、承認資料のスライドの内容を Claude が組み立てる。
2. HTML のスライドを正本にして、PowerPoint で編集できる PPTX（図形・文字・表・グラフ）を出す。
3. はみ出し・重なり・最小文字サイズなど、崩れを検査して、崩れたまま出さない。
4. 利用者が、できあがる前に案を見て、選び、直せる（承認は 1 回）。
5. 後から直す・作り直す。

**付加（あれば便利だが、中核ではない）**

- 自分のテンプレートの上に作る
- 型にない図を絵にする
- HTML 出力
- 配色・文字サイズの調整
- 画面上での直接編集
- 手直しした PPTX の上書き保護
