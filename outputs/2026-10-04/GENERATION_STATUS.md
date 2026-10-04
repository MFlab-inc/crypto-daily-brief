level: L0
call_A: OK（1回試行）
call_B: OK（1回試行）
token_usage（実消費量）: input=30567, output=2902 (call_A: in=24734 out=2732 / call_B: in=5833 out=170)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続39日以上
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
  - Cointelegraph: ok（対象日5件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続39日以上
  - The Block: ok（対象日0件／取得19件）
  - Google News (Reuters検索): ok（対象日49件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 24件 / audit_ledger: 24件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持1件／除外0件（call_Aへ渡した前日以前の投稿: 2026-10-03・2026-10-02・2026-09-30）
  - 保持: 「米地域銀行団体がOCCを相手取り、暗号通貨企業への信託銀行免許付与の是非を争う訴訟の動向が注視されています（CoinDesk、Cointelegraph、10月…」
24時間レンジ不整合検出: BTC・ETH・BNB（終値が取得したレンジの範囲外のため、本文の24時間レンジ行を省略）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS15・SKIP2〔C22・C26〕・FAIL0）
  FAILしたチェックはありません。
向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告なし（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0）

月次累計（2026-10）: input=233535, output=36285（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
