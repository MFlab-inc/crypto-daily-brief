level: L1
call_A: FAILED (ValueError: JSON応答がオブジェクトでない / 3回試行)
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: OutputTruncatedError: 出力が上限（max_tokens=8000）で打ち切られた
    2試行目: ValueError: 必須キー欠落: ['headline_for_image', 'part1_headline', 'part1_points', 'reusable_for_summary', 'audit_ledger']
    3試行目: ValueError: JSON応答がオブジェクトでない
call_B: OK（1回試行）
token_usage（実消費量）: input=115754, output=22722 (call_A: in=108538 out=22602 / call_B: in=7216 out=120)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続73日以上
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日0件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日1件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日3件／取得25件）
  - Cointelegraph: ok（対象日6件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続73日以上
  - The Block: ok（対象日3件／取得20件）
  - Google News (Reuters検索): ok（対象日48件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 28件 / audit_ledger: N/A件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier2候補（Reuters）: 収集窓内48件 → 15件を選定（関連度順）・33件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 11/06 22:46〜11/07 21:04（JST 11/07 07:46〜11/08 06:04）
  除外した記事の公開時刻: GMT 11/06 23:01〜11/07 17:37（JST 11/07 08:01〜11/08 02:37）
収集窓: GMT 11/06 22:00〜11/07 22:00（JST 11/07 07:00〜11/08 07:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-11-07/candidates_log.json（全61件の選定状態・公開時刻・呼び出しAの採否と理由）

手当が必要な箇所:
  - 前編【ヘッドライン】
  - 前編【主要なポイント】

自動生成できた箇所:
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS13・SKIP4〔C19・C21・C22・C26〕・FAIL0）
  FAILしたチェックはありません。
向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告なし（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用0・見出しの繰り返し0・重複の根拠が弱い0）

月次累計（2026-11）: input=602706, output=83693（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
