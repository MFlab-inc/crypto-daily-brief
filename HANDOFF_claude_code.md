# Claude Code 引き継ぎ指示書（フェーズ1：図版＋APR画像の無人生成）

## あなた（Claude Code）への依頼

このフォルダ一式を現在のリポジトリにコミットし、GitHub Actionsでの初回実行を成功させてください。
設計・仕様の決定は完了済みです。**品質ゲート・待機時間・固定レイアウトを緩和する変更は行わないでください。**
問題があれば修正はコード側で行い、仕様変更が必要と思われる場合は作業を止めて報告してください。

## 前提（設定済み）

- リポジトリSecrets: `CMC_API_KEY`（CoinMarketCap Basic）設定済み。`ANTHROPIC_API_KEY` はフェーズ1では未使用。
- 仕様の正本: `docs/recovered/` に統合運用基準・品質チェック・自動納品契約ほか回収文書を置くこと（ユーザーがアップロード済みのファイル群）。

## 手順

1. 本フォルダの内容をリポジトリ直下に配置してコミット（`outputs/` は空でよい）。
2. Actionsタブ → `daily-crypto-brief` → **Run workflow** で手動実行（workflow_dispatch）。
3. 失敗したステップのログを読み、環境起因の問題（依存・フォント・パス）を修正して再実行。
4. 成功したら `outputs/<対象日>/` の5点を確認:
   `daily_data.json` / `raw_data.json` / `infographic.png` / `apr_screenshot.jpg` / `final_audit_*.json`
5. `final_audit` が `overall: PASS, failed: 0` であることを確認し、実行結果を報告。

## 初回実行で検証が必要な箇所（コード内コメントにも記載）

| 箇所 | 内容 | 対処 |
|---|---|---|
| `fetch_data.py: fetch_base_dex_volume` | DefiLlama `/overview/dexs/base` のルート `total24h` の存在は初回実行で要確認（フォールバックとしてprotocols合算を実装済み） | 実レスポンスで確認し、必要ならパース修正 |
| `fetch_data.py: fetch_usdc_dominance_base` | `stablecoins.llama.fi/stablecoins` の `chainCirculating.Base` 構造を要確認 | 取得失敗時は「未確認」に落ちる設計。壊さず修正 |
| `fetch_data.py` の各フォーマッタ | 桁・丸めは8/9・8/10のManus実出力から逆算した近似 | シャドー比較で差があれば報告（勝手に基準を変えない） |
| `infographic_renderer.py` | フォントパス `/usr/share/fonts/opentype/noto/NotoSansCJK-*.ttc` は `fonts-noto-cjk` で入る想定 | 出力PNGの日本語を必ず目視確認 |
| `capture_apr.py` | Playwright+Firefox移植。待機3/8/最大3試行・クロップ座標は原版と同一（変更禁止） | クロップ結果に6カード全体＋上段メトリクスが収まるか目視確認 |

## 絶対に変えないもの

- 検証ゲート（`verify_data.py`）の合格条件・フェイルクローズ（failed>0でコミットしない）
- 「未確認」を推測値で埋めない方針
- Fear & Greed の取得元（CMC `/v3/fear-and-greed/latest`。Alternative.me は使用禁止）
- 図版の固定レイアウト・配色・2560×1440
- APR撮影の待機・再試行・クロップ座標

## 成功後にユーザーへ報告する内容

1. 実行結果（PASS/FAIL、final_auditの要約）
2. 生成された `infographic.png` と `apr_screenshot.jpg` の確認依頼
3. 上表の検証箇所で実際に直した点
4. 翌朝07:30 JSTの自動実行が有効になっている旨

## フェーズ2（今回はやらない・別途chatで台本作成後）

- X投稿 前編/後編の生成（Claude API + web検索によるニュース選定 = 編集工程）
- bitFlyer/Coincheck 取得と国内2社×DEX比較行（後編用）
- `prepare_delivery_package.py` / `validate_delivery_package.py` の再実装と受入試験A-01〜A-05のpytest化
- 外部AI監査用パッケージ（逐語引用付き）の自動生成

## 切替チェックリスト（ユーザー向けメモ・READMEにも記載）

- シャドー数日でManus出力と差分照合 → 合格後に本番扱い
- **Manus側の定期タスク「クリプト前日市況」を停止**（8/25復元後の二重生成防止）
