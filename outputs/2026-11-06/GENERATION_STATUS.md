⚠⚠ 警告1件（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式0・媒体名照合0・地政学の不採用0・行頭の記号0・見出し理由の不採用0・見出しの繰り返し0・重複の根拠が弱い1） — FAILではありません（機械監査の合否には影響しません）。投稿前に本文を見直してください。
  ⚠ [重複の根拠が弱い] 「重複」を理由に不採用にした候補のうち、根拠が弱いものが3件あります。同じ区分でも発言者や内容が違えば別の事実です（Bの扱いの基準の4(c)）。重複先と同じ事実かを確認してください（題名の語の重なりによる検知で、実際の重複でも言い換えで拾うことがあります）。 ・候補17「US labor market regains ground as job growth surges, unemplo…」（重複先の候補と題名に共通する語が無い。重複先: 候補10「What They Are Saying: Blowout October Jobs Report …」。理由: B: 候補10と同じ雇用統計の重複） ・候補25「Gold drops as strong US payrolls boost dollar, yields - Reut…」（重複先の候補と題名に共通する語が無い。重複先: 候補10「What They Are Saying: Blowout October Jobs Report …」。理由: B: 候補10と同じ雇用統計を受けたドル高・金安の重複） ・候補26「Dollar index jumps after US payrolls beat forecasts - Reuter…」（重複先の候補と題名に共通する語が無い。重複先: 候補10「What They Are Saying: Blowout October Jobs Report …」。理由: B: 候補10と同じ雇用統計を受けたドル高の重複）

level: L0
call_A: OK（2回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: OutputTruncatedError: 出力が上限（max_tokens=8000）で打ち切られた
    2試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=112181, output=13318 (call_A: in=104055 out=12708 / call_B: in=8126 out=610)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続72日以上
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日1件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日6件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日1件／取得10件）
  - ホワイトハウス: ok（対象日5件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日1件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日14件／取得25件）
  - Cointelegraph: ok（対象日24件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続72日以上
  - The Block: ok（対象日16件／取得20件）
  - Google News (Reuters検索): ok（対象日50件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 52件 / audit_ledger: 52件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持0件／除外0件（call_Aへ渡した前日以前の投稿: 2026-11-05・2026-11-04・2026-11-03）
tier2候補（Reuters）: 収集窓内50件 → 15件を選定（関連度順）・35件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 11/05 23:15〜11/06 21:40（JST 11/06 08:15〜11/07 06:40）
  除外した記事の公開時刻: GMT 11/05 22:58〜11/06 21:42（JST 11/06 07:58〜11/07 06:42）
tier3候補 54件中 23件を選定（31件を件数上限により除外）
独立2媒体ペア救済: 4組（8件を上限外で追加）
収集窓: GMT 11/05 22:00〜11/06 22:00（JST 11/06 07:00〜11/07 07:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-11-06/candidates_log.json（全118件の選定状態・公開時刻・呼び出しAの採否と理由）

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

月次累計（2026-11）: input=486952, output=60971（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
