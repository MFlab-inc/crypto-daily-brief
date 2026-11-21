level: L1
call_A: FAILED (force_drop_unresolvedで続行したが除外後の再監査（C12〜C28）がFAILしたためL1へフォールバック（FAILしたチェック: ['C28_headline_points_role_separation']） / 3回試行)
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: OutputTruncatedError: 出力が上限（max_tokens=8000）で打ち切られた
    2試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [25]
      相方が成立しなかった候補の内訳（2試行目）:
        - 候補ID25 [The Block] 「Cyber investigating suspected $1 million bridge exploit as Upbit, Bith…」
            ・自身の申告: no_claim（相方の申告なし（pairs_with_candidate_id=null））
    3試行目: 強制不採用（候補ID [38]）で続行 → 再監査FAILのためL1へフォールバック
      相方が成立しなかった候補の内訳（3試行目）:
        - 候補ID38 [CoinDesk] 「Kalshi races to get ahead of New York order that could shut down excha…」
            ・自身の申告→ID24 [The Block] 「Kalshi faces Monday hearing on New York order it s…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
call_B: OK（1回試行）
token_usage（実消費量）: input=139697, output=16243 (call_A: in=124871 out=15617 / call_B: in=7215 out=109)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続87日以上
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日0件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日6件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日2件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日8件／取得25件）
  - Cointelegraph: ok（対象日4件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続87日以上
  - The Block: ok（対象日4件／取得20件）
  - Google News (Reuters検索): ok（対象日49件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 38件 / audit_ledger: N/A件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier2候補（Reuters）: 収集窓内49件 → 15件を選定（関連度順）・34件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 11/21 04:10〜11/21 19:55（JST 11/21 13:10〜11/22 04:55）
  除外した記事の公開時刻: GMT 11/20 22:43〜11/21 13:04（JST 11/21 07:43〜11/21 22:04）
tier3候補 16件中 15件を選定（1件を件数上限により除外）
収集窓: GMT 11/20 22:00〜11/21 22:00（JST 11/21 07:00〜11/22 07:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-11-21/candidates_log.json（全73件の選定状態・公開時刻・呼び出しAの採否と理由）
call_A 強制不採用（v1.79）: 最終試行でも独立2ソースの相方が成立しなかった1件を強制的に不採用にして続行しました。
  - candidate_id=38 title='Kalshi races to get ahead of New York order that could shut down exchange' source='CoinDesk': 最終試行でも独立2ソースの相方が成立しなかったため強制的に不採用にした
call_A 強制不採用後の再監査（C12〜C28）がFAILしたため、call_Aを失敗扱いへ差し戻しL1へフォールバックしました（FAILしたチェック: ['C28_headline_points_role_separation']）。
  FAIL: C28_headline_points_role_separation — ヘッドラインの同一文に銘柄名と値動き語が存在（統合運用基準§3.1: ヘッドラインに価格・値動きを書かない。誤検知時は config/c28_allowlist.json へ登録）: ["['ビットコイン']×['下落', '反発']（Reutersによると、ビットコインは一時2年ぶりの安値まで下落した後、反発して6万ドルを回復したと報じられました）"]

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

月次累計（2026-11）: input=1925876, output=252640（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
