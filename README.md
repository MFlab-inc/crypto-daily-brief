# crypto-daily-brief（フェーズ1）

毎朝07:30 JSTに、前日対象の暗号通貨市況インフォグラフィック（2560×1440）と
#ETH/#USDC（Base）APR実画面を無人生成し、機械監査PASS時のみ `outputs/<対象日>/` へコミットする。
X投稿（前編・後編）の編集生成はフェーズ2。仕様の正本は `docs/recovered/` の統合運用基準ほか。

## 構成
- `scripts/fetch_data.py` … データ取得→daily_data.json（LLM不使用）
- `scripts/infographic_renderer.py` … 回収済み固定レンダラー（原本のまま）
- `scripts/capture_apr.py` … APR実画面撮影（原版の待機・座標を維持）
- `scripts/verify_data.py` … 機械監査→final_audit（failed>0でフェイルクローズ）
- `.github/workflows/daily.yml` … 07:30 JST cron＋手動実行

## 初回セットアップ
1. Secrets: `CMC_API_KEY`（設定済み）
2. `HANDOFF_claude_code.md` に従いClaude Codeで初回実行・検証
3. シャドー数日 → Manus出力と差分照合 → 切替

## 切替時チェックリスト
- [ ] Manus定期タスク「クリプト前日市況」を停止（二重生成防止）
- [ ] cron時刻の最終確認（現在 07:30 JST）
- [ ] 回収文書一式を docs/recovered/ にコミット済みであること
