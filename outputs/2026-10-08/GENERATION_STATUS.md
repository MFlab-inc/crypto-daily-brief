level: L0
call_A: OK（3回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: JSONDecodeError: Expecting ',' delimiter: line 57 column 177 (char 8178)
    2試行目: JSONDecodeError: Expecting property name enclosed in double quotes: line 3 column 3 (char 60)
    3試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=149324, output=23711 (call_A: in=141888 out=22900 / call_B: in=7436 out=811)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日1件／取得20件）
  - FRB（speeches）: ok（対象日1件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続43日以上
  - OCC: ok（対象日1件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日6件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日1件／取得10件）
  - ホワイトハウス: ok（対象日4件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日24件／取得25件）
  - Cointelegraph: ok（対象日22件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続43日以上
  - The Block: ok（対象日12件／取得20件）
  - Google News (Reuters検索): ok（対象日49件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 52件 / audit_ledger: 52件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持0件／除外0件（call_Aへ渡した前日以前の投稿: 2026-10-07・2026-10-06・2026-10-05）
tier2候補（Reuters）: 収集窓内49件 → 15件を選定・34件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 10/08 14:56〜10/08 20:50（JST 10/08 23:56〜10/09 05:50）
  除外した記事の公開時刻: GMT 10/07 23:13〜10/08 14:36（JST 10/08 08:13〜10/08 23:36）
tier3候補 58件中 23件を選定（35件を件数上限により除外）
独立2媒体ペア救済: 5組（8件を上限外で追加）
収集窓: GMT 10/07 21:00〜10/08 21:00（JST 10/08 06:00〜10/09 06:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-10-08/candidates_log.json（全121件の選定状態・公開時刻・呼び出しAの採否と理由）
audit_ledger自動補完: 9件（decision/reasonが空だったため定型文で補完。C19は空欄検知のためPASSする——理由の質は監査対象外）

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

月次累計（2026-10）: input=649411, output=94807（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
