⚠⚠ 警告2件（向きの食い違い0・見出しのタグ0・指標日の見出し1・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用0・見出しの繰り返し0・重複の根拠が弱い1） — FAILではありません（機械監査の合否には影響しません）。投稿前に本文を見直してください。
  ⚠ [指標日の見出し] 指標日（PCE: Core PCE Price Index m/m）に対応しうる材料が採用されていますが、ヘッドラインはPCEに触れていません（主要なポイントの1番目は触れています）。 採用された対応候補: 「Fed policymakers at odds over causes of high inflation - Reuters」［Reuters］（計2件）／ヘッドライン: 「Reutersによると、米国の第3四半期GDP成長率（改定値）は市場予想を上回る大幅な上方修正になったと報じられました。」。暗号通貨に直接関わる大型の制度材料が公式発表で確認できる日（見出しはその材料、指標は主要なポイントの1番目）は規則どおりです。目視で確認してください。
  ⚠ [重複の根拠が弱い] 「重複」を理由に不採用にした候補のうち、根拠が弱いものが1件あります。同じ区分でも発言者や内容が違えば別の事実です（Bの扱いの基準の4(c)）。重複先と同じ事実かを確認してください（題名の語の重なりによる検知で、実際の重複でも言い換えで拾うことがあります）。 ・候補43「Bitcoin falls toward $57K amid US tariff fears, hot PCE data…」（重複先の候補と題名に共通する語が無い。重複先: 候補17「Fed policymakers at odds over causes of high infla…」。理由: B: 候補17・19・23と同じ事実（関税懸念とPCE統計）の重複に相当し、単独tier3のため不採用）

level: L0
call_A: OK（2回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [33, 37, 38, 40, 49, 51, 53]
      相方が成立しなかった候補の内訳（1試行目）:
        - 候補ID33 [Cointelegraph] 「Braiins warns of Bitcoin mining attacks affecting over 1,000 sites」
            ・自身の申告→ID35 [The Block] 「Bitcoin miners hit by hashrate hijacking attack ex…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
        - 候補ID37 [Cointelegraph] 「Ethereum Foundation backs Keccak-256 to counter quantum, AI threats」
            ・自身の申告→ID47 [The Block] 「Ethereum Foundation researchers pick one hash ‘to …」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
        - 候補ID38 [CoinDesk] 「French Senate blocks new crypto tax and wallet list critics called a k…」
            ・自身の申告→ID48 [Cointelegraph] 「French Senate rejects 100K euro crypto wallet disc…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
        - 候補ID40 [The Block] 「Nvidia agrees to $290 million settlement over crypto mining disclosure…」
            ・自身の申告→ID45 [Cointelegraph] 「Nvidia agrees to $290M settlement over crypto mini…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
        - 候補ID49 [CoinDesk] 「Ukrainian lawmakers pass crypto tax and regulation bill expected to br…」
            ・自身の申告→ID50 [Cointelegraph] 「Ukraine passes bill to legalize crypto and tax pro…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
        - 候補ID51 [Cointelegraph] 「Japan’s SBI, SMFG launch Solana venture for stablecoins, tokenization」
            ・自身の申告→ID52 [The Block] 「Japan’s SBI, SMFG launch Solana joint venture for …」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
        - 候補ID53 [Cointelegraph] 「Hong Kong launches tokenized debt platform with 24-hour settlement」
            ・自身の申告→ID54 [The Block] 「Hong Kong Monetary Authority launches digital asse…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
    2試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=107263, output=13759 (call_A: in=99239 out=13012 / call_B: in=8024 out=747)
news_sources:
  - SEC: ok（対象日1件／取得25件）
  - FRB: ok（対象日2件／取得20件）
  - FRB（speeches）: ok（対象日1件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続91日以上
  - OCC: ok（対象日1件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日5件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日3件／取得10件）
  - ホワイトハウス: ok（対象日2件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日1件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日17件／取得25件）
  - Cointelegraph: ok（対象日23件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続91日以上
  - The Block: ok（対象日19件／取得20件）
  - Google News (Reuters検索): ok（対象日49件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 54件 / audit_ledger: 54件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持0件／除外0件（call_Aへ渡した前日以前の投稿: 2026-11-24・2026-11-23・2026-11-22）
tier2候補（Reuters）: 収集窓内49件 → 15件を選定（関連度順）・34件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 11/25 01:26〜11/25 20:50（JST 11/25 10:26〜11/26 05:50）
  除外した記事の公開時刻: GMT 11/25 00:02〜11/25 21:29（JST 11/25 09:02〜11/26 06:29）
tier3候補 59件中 23件を選定（36件を件数上限により除外）
独立2媒体ペア救済: 5組（8件を上限外で追加）
収集窓: GMT 11/24 22:00〜11/25 22:00（JST 11/25 07:00〜11/26 07:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-11-25/candidates_log.json（全124件の選定状態・公開時刻・呼び出しAの採否と理由）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

局所修正（repair_post.py・C18/C13）:
  ラウンド1（対象: C18_causal_assertion）:
    [C18_causal_assertion / part1_points] OK
      修正前: ・Reutersによると、イエメンのフーシ派はサウジアラビア最大級の製油所を攻撃したと主張し、これを受けて原油価格は上昇したと報じられました
      修正後: ・Reutersによると、イエメンのフーシ派はサウジアラビア最大級の製油所を攻撃したと主張し、これを受けて原油価格は上昇した可能性があります
  修正呼び出し合計トークン: input=734, output=78
  最終結果: 救済（C18・C13ともPASSへ改善）

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS17・SKIP0・FAIL0）
  FAILしたチェックはありません。
向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告2件（向きの食い違い0・見出しのタグ0・指標日の見出し1・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用0・見出しの繰り返し0・重複の根拠が弱い1）（ファイル先頭に表示）

月次累計（2026-11）: input=2391932, output=307808（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
