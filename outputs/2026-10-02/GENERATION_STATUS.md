level: L0
call_A: OK（2回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [39, 42]
      相方が成立しなかった候補の内訳（1試行目）:
        - 候補ID39 [CoinDesk] 「Once a $2 billion Ethereum layer-2, Blast is shutting down after asset…」
            ・自身の申告→ID42 [The Block] 「Paradigm-backed Layer 2 Blast to wind down network…」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
            ・ID42 [The Block] 「Paradigm-backed Layer 2 Blast to wind down network…」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
        - 候補ID42 [The Block] 「Paradigm-backed Layer 2 Blast to wind down network as costs exceed rev…」
            ・自身の申告→ID39 [CoinDesk] 「Once a $2 billion Ethereum layer-2, Blast is shutt…」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
            ・ID39 [CoinDesk] 「Once a $2 billion Ethereum layer-2, Blast is shutt…」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
    2試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=70217, output=11341 (call_A: in=64056 out=10837 / call_B: in=6161 out=504)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日3件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日5件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日4件／取得10件）
  - ホワイトハウス: ok（対象日5件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日1件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日11件／取得25件）
  - Cointelegraph: ok（対象日27件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - The Block: ok（対象日9件／取得19件）
  - Google News (Reuters検索): ok（対象日47件／取得50件）
news_candidates_today: 50件 / audit_ledger: 50件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier3候補 47件中 17件を選定（30件を件数上限により除外）
独立2媒体ペア救済: 1組（2件を上限外で追加）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS
  FAILしたチェックはありません。
向きの食い違いチェック（警告のみ・FAILにしない）: 警告なし

月次累計（2026-10）: input=174320, output=29717（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
