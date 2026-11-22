level: L0
call_A: OK（3回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: ValueError: 空応答
    2試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [18, 24]
      相方が成立しなかった候補の内訳（2試行目）:
        - 候補ID18 [The Block] 「Chainflip’s losses climb to $12 million after protocol discloses 122.9…」
            ・自身の申告→ID24 [Cointelegraph] 「Chainflip confirms $12M hack, offers attacker 10% …」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.38＜閾値0.4）
            ・ID24 [Cointelegraph] 「Chainflip confirms $12M hack, offers attacker 10% …」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.38＜閾値0.4）
        - 候補ID24 [Cointelegraph] 「Chainflip confirms $12M hack, offers attacker 10% bounty」
            ・自身の申告→ID18 [The Block] 「Chainflip’s losses climb to $12 million after prot…」: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.38＜閾値0.4）
            ・ID18 [The Block] 「Chainflip’s losses climb to $12 million after prot…」からの申告: overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.38＜閾値0.4）
    3試行目: 成功
call_B: OK（1回試行）
call_B フロー書式の再生成（v1.101）: 【市場のフロー】の書式のWARNが1本出たため、call_Bを1回再生成しました。採用: 再生成後の版（再生成後は書式違反が解消しました）。
  再生成前の連鎖（WARN1件）:
    ・【出来事・ニュース】Reutersによると、イエメンのフーシ派はサウジアラビアのラビグ製油所を攻撃したと主張したと報じられました。被害・影響は未確認です → 【地政学・マクロの変化】中東情勢の緊迫化が意識された可能性がある変化として受け止められました → 【暗号通貨価格】 #BTC +0.98%、 #ETH +1.87%（24時間比）で、同時期は小幅な上昇となりました。
    ↳ 1本目の違反: 1文でない（句点が末尾の1つだけでない。全角括弧内は除く）
  再生成後の連鎖（WARN0件）:
    ・【出来事・ニュース】Reutersによると、イエメンのフーシ派はサウジアラビアのラビグ製油所を攻撃したと主張したと報じられました（被害・影響は未確認） → 【地政学・マクロの変化】中東情勢の緊迫化が意識された可能性がある変化として受け止められました → 【暗号通貨価格】 #BTC +0.98%、 #ETH +1.87%（24時間比）で、同時期は小幅な上昇でした。
  再生成の使用量は、token_usageの合計に含まれています（再生成分: 入力8305・出力241トークン）。
token_usage（実消費量）: input=118188, output=13237 (call_A: in=102549 out=12749 / call_B: in=7334 out=247)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続88日以上
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日0件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日0件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日2件／取得25件）
  - Cointelegraph: ok（対象日5件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続88日以上
  - The Block: ok（対象日2件／取得20件）
  - Google News (Reuters検索): ok（対象日50件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 24件 / audit_ledger: 24件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持0件／除外0件（call_Aへ渡した前日以前の投稿: 2026-11-20・2026-11-19・2026-11-18）
tier2候補（Reuters）: 収集窓内50件 → 15件を選定（関連度順）・35件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 11/22 06:55〜11/22 21:54（JST 11/22 15:55〜11/23 06:54）
  除外した記事の公開時刻: GMT 11/21 23:03〜11/22 17:16（JST 11/22 08:03〜11/23 02:16）
収集窓: GMT 11/21 22:00〜11/22 22:00（JST 11/22 07:00〜11/23 07:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-11-22/candidates_log.json（全59件の選定状態・公開時刻・呼び出しAの採否と理由）

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

月次累計（2026-11）: input=2044064, output=265877（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
