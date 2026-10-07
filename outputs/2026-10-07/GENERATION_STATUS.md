⚠⚠ 警告1件（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用1・見出しの繰り返し0・重複の根拠が弱い0） — FAILではありません（機械監査の合否には影響しません）。投稿前に本文を見直してください。
  ⚠ [見出し理由の不採用] ヘッドラインにしないこと（または他に採用する材料があること）を理由に不採用にした候補が1件あります。見出しの主題にするかと、主要なポイントに載せるかは別の判断です（Bの扱いの基準の6）。主要なポイントに載せる判断を確認してください（理由の言い回しによる検知で、不採用が誤りだとは断定しません）。 ・USTR「Fourteen Economies Join the United States in Signing a Joint Ministerial Stateme…」（理由: B: 製造業の過剰生産能力に関する通商声明で、暗号通貨市場への波及経路を具体的に説明できず、他の採用材料がある中で優先対象に当たらない）

level: L0
call_A: OK（2回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [40, 41]
      相方が成立しなかった候補の内訳（1試行目）:
        - 候補ID40 [CoinDesk] 「Tether tapped by Kazakhstan’s central bank to explore stablecoin and t…」
            ・自身の申告→ID34 [Cointelegraph] 「Tether, Kazakhstan cenbank mull tenge stablecoin a…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
        - 候補ID41 [The Block] 「Coinbase Pro to return; Deribit integration creates Coinbase Global Ex…」
            ・自身の申告→ID36 [Cointelegraph] 「Coinbase brings global crypto derivatives liquidit…」: target_use_false（申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する）
    2試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=97791, output=14411 (call_A: in=90428 out=13690 / call_B: in=7363 out=721)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日1件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続42日以上
  - OCC: ok（対象日1件／取得10件）
  - CFTC: failed（HTTP 403）・連続1日（新規）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: failed（ReadTimeout: HTTPSConnectionPool(host='www.boj.or.jp', port=443): Read timed out. (read timeout=15)）・連続1日（新規）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日1件／取得10件）
  - ホワイトハウス: ok（対象日4件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日2件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日20件／取得25件）
  - Cointelegraph: ok（対象日22件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続42日以上
  - The Block: ok（対象日10件／取得20件）
  - Google News (Reuters検索): ok（対象日47件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 47件 / audit_ledger: 47件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持0件／除外0件（call_Aへ渡した前日以前の投稿: 2026-10-06・2026-10-05・2026-10-03）
tier2候補（Reuters）: 収集窓内47件 → 15件を選定・32件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 10/07 15:01〜10/07 20:19（JST 10/08 00:01〜10/08 05:19）
  除外した記事の公開時刻: GMT 10/06 22:44〜10/07 14:56（JST 10/07 07:44〜10/07 23:56）
tier3候補 52件中 23件を選定（29件を件数上限により除外）
独立2媒体ペア救済: 5組（8件を上限外で追加）
収集窓: GMT 10/06 21:00〜10/07 21:00（JST 10/07 06:00〜10/08 06:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-10-07/candidates_log.json（全108件の選定状態・公開時刻・呼び出しAの採否と理由）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS17・SKIP0・FAIL0）
  FAILしたチェックはありません。
向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告1件（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用1・見出しの繰り返し0・重複の根拠が弱い0）（ファイル先頭に表示）

月次累計（2026-10）: input=500087, output=71096（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
