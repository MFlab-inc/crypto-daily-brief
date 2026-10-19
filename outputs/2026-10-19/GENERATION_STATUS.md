level: L0
call_A: OK（2回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [26, 29, 35]
      相方が成立しなかった候補の内訳（1試行目）:
        - 候補ID26 [CoinDesk] 「Tether: Senator's investigation misses positive work that's led to low…」
            ・自身の申告: no_claim（相方の申告なし（pairs_with_candidate_id=null））
        - 候補ID29 [Cointelegraph] 「Visa, Mesh partner to enable crypto spending at 175M merchant location…」
            ・自身の申告→ID35 [The Block] 「Mesh taps Visa to let users spend crypto without a…」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.36＜閾値0.4）
            ・ID35 [The Block] 「Mesh taps Visa to let users spend crypto without a…」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.36＜閾値0.4）
        - 候補ID35 [The Block] 「Mesh taps Visa to let users spend crypto without a separate card」
            ・自身の申告→ID29 [Cointelegraph] 「Visa, Mesh partner to enable crypto spending at 17…」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.36＜閾値0.4）
            ・ID29 [Cointelegraph] 「Visa, Mesh partner to enable crypto spending at 17…」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.36＜閾値0.4）
    2試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=98177, output=11390 (call_A: in=90619 out=10911 / call_B: in=7558 out=479)
news_sources:
  - SEC: ok（対象日1件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続54日以上
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日1件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日2件／取得10件）
  - ホワイトハウス: ok（対象日4件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日1件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日17件／取得25件）
  - Cointelegraph: ok（対象日22件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続54日以上
  - The Block: ok（対象日11件／取得20件）
  - Google News (Reuters検索): ok（対象日49件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 45件 / audit_ledger: 45件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持1件／除外0件（call_Aへ渡した前日以前の投稿: 2026-10-18・2026-10-17・2026-10-16）
  - 保持: 「ウクライナによるロシア石油施設への攻撃やホルムズ海峡を巡る緊張など地政学材料が報じられましたが、当日時点で新たな進展は確認できていません（Reuters、10月…」
tier2候補（Reuters）: 収集窓内49件 → 15件を選定（関連度順）・34件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 10/18 23:06〜10/19 18:39（JST 10/19 08:06〜10/20 03:39）
  除外した記事の公開時刻: GMT 10/18 23:00〜10/19 20:54（JST 10/19 08:00〜10/20 05:54）
tier3候補 50件中 21件を選定（29件を件数上限により除外）
独立2媒体ペア救済: 4組（6件を上限外で追加）
収集窓: GMT 10/18 21:00〜10/19 21:00（JST 10/19 06:00〜10/20 06:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-10-19/candidates_log.json（全108件の選定状態・公開時刻・呼び出しAの採否と理由）
24時間レンジ不整合検出: BNB（終値が取得したレンジの範囲外のため、本文の24時間レンジ行を省略）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS17・SKIP0・FAIL0）
  FAILしたチェックはありません。
向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告なし（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用0・見出しの繰り返し0・重複の根拠が弱い0）

月次累計（2026-10）: input=1352799, output=184155（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
