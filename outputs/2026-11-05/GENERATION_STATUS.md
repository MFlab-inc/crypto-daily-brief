⚠⚠ 警告1件（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用0・見出しの繰り返し0・重複の根拠が弱い1） — FAILではありません（機械監査の合否には影響しません）。投稿前に本文を見直してください。
  ⚠ [重複の根拠が弱い] 「重複」を理由に不採用にした候補のうち、根拠が弱いものが1件あります。同じ区分でも発言者や内容が違えば別の事実です（Bの扱いの基準の4(c)）。重複先と同じ事実かを確認してください（題名の語の重なりによる検知で、実際の重複でも言い換えで拾うことがあります）。 ・候補21「Brent crude jumps, settles up over $3 after tanker attacks -…」（重複先の候補と題名に共通する語が無い。重複先: 候補19「Iran's IRGC says two tankers and tugboat caught fi…」。理由: B: 同じtierの候補19と同じ事実（タンカー攻撃を受けた原油価格上昇）の重複）

level: L0
call_A: OK（2回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [25, 36]
      相方が成立しなかった候補の内訳（1試行目）:
        - 候補ID25 [The Block] 「Bitcoin erases post-election gains as Wall Street selloff triggers ove…」
            ・自身の申告→ID36 [Cointelegraph] 「Bitcoin crashes 6% to 7-week low as US stocks eras…」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
            ・ID36 [Cointelegraph] 「Bitcoin crashes 6% to 7-week low as US stocks eras…」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
        - 候補ID36 [Cointelegraph] 「Bitcoin crashes 6% to 7-week low as US stocks erase election gains」
            ・自身の申告→ID25 [The Block] 「Bitcoin erases post-election gains as Wall Street …」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
            ・ID25 [The Block] 「Bitcoin erases post-election gains as Wall Street …」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）
    2試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=91604, output=11332 (call_A: in=84003 out=10606 / call_B: in=7601 out=726)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日1件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続71日以上
  - OCC: ok（対象日1件／取得10件）
  - CFTC: ok（対象日1件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日3件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日2件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日25件／取得25件）
  - Cointelegraph: ok（対象日22件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続71日以上
  - The Block: ok（対象日10件／取得20件）
  - Google News (Reuters検索): ok（対象日50件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 44件 / audit_ledger: 44件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持0件／除外0件（call_Aへ渡した前日以前の投稿: 2026-11-04・2026-11-03・2026-11-02）
tier2候補（Reuters）: 収集窓内50件 → 15件を選定（関連度順）・35件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 11/04 23:38〜11/05 20:58（JST 11/05 08:38〜11/06 05:58）
  除外した記事の公開時刻: GMT 11/04 23:02〜11/05 21:39（JST 11/05 08:02〜11/06 06:39）
tier3候補 57件中 21件を選定（36件を件数上限により除外）
独立2媒体ペア救済: 3組（6件を上限外で追加）
収集窓: GMT 11/04 22:00〜11/05 22:00（JST 11/05 07:00〜11/06 07:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-11-05/candidates_log.json（全115件の選定状態・公開時刻・呼び出しAの採否と理由）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS17・SKIP0・FAIL0）
  FAILしたチェックはありません。
向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告1件（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用0・見出しの繰り返し0・重複の根拠が弱い1）（ファイル先頭に表示）

月次累計（2026-11）: input=374771, output=47653（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
