⚠⚠ 警告2件（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式2・媒体名照合0・地政学の不採用0） — FAILではありません（機械監査の合否には影響しません）。投稿前に本文を見直してください。
  ⚠ [フロー書式] 市場のフローの1本目が書式（統合運用基準§3.3）から外れています: 【出来事・ニュース】が無い・【出来事・ニュース】で始まっていない・「→」の直後がラベルでない。 連鎖: 「①CFTCが商品取引法に基づく暗号資産取引・市場の規制枠組み整備に向けた事前規則制定案を発表し、意見募集を開始したと公式に表明しました（CFTC、Reuters、10月5日） → 【地政学・マクロの変…」
  ⚠ [フロー書式] 市場のフローの2本目が書式（統合運用基準§3.3）から外れています: 【出来事・ニュース】が無い・【出来事・ニュース】で始まっていない・「→」の直後がラベルでない。 連鎖: 「②FinCENが暗号資産ミキシングサービスを主要なマネーロンダリング上の懸念と指定する規則案等を撤回したと複数の専門媒体が報じました（The Block、Cointelegraph、10月5日） → …」

level: L0
call_A: OK（3回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [43]
      相方が成立しなかった候補の内訳（1試行目）:
        - 候補ID43 [CoinDesk] 「Kraken operator Payward and Singapore Gulf Bank partner for 24/7 insti…」
            ・自身の申告→ID44 [Cointelegraph] 「Kraken parent adds 24/7 dollar settlement with Sin…」: target_use_false（申告先がuse:false（不採用））
    2試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [33]
      相方が成立しなかった候補の内訳（2試行目）:
        - 候補ID33 [The Block] 「Treasury withdraws crypto mixing rule, citing concerns over ‘chilling …」
            ・自身の申告→ID26 [Cointelegraph] 「FinCEN withdraws proposed crypto mixing rule over …」: target_use_false（申告先がuse:false（不採用））
    3試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=118868, output=14592 (call_A: in=112591 out=14007 / call_B: in=6277 out=585)
news_sources:
  - SEC: ok（対象日1件／取得25件）
  - FRB: ok（対象日1件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）・連続40日以上
  - OCC: ok（対象日1件／取得10件）
  - CFTC: ok（対象日2件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日3件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日1件／取得10件）
  - ホワイトハウス: ok（対象日1件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日19件／取得25件）
  - Cointelegraph: ok（対象日21件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）・連続40日以上
  - The Block: ok（対象日11件／取得19件）
  - Google News (Reuters検索): ok（対象日50件／取得50件）
  ※「連続○日」は本日を含み、GENERATION_STATUS.mdが残っている日だけを数えます（記録の無い日は数えず、連続を途切れさせません）。「以上」は、最も古い記録まで遡っても回復が見つからず、それ以前の状況が不明なことを表します。
news_candidates_today: 48件 / audit_ledger: 48件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持0件／除外0件（call_Aへ渡した前日以前の投稿: 2026-10-03・2026-10-02・2026-09-30）
tier2候補（Reuters）: 収集窓内50件 → 15件を選定・35件を件数上限（15件）により除外
  選定した記事の公開時刻: GMT 10/05 15:33〜10/05 20:45（JST 10/06 00:33〜10/06 05:45）
  除外した記事の公開時刻: GMT 10/04 23:03〜10/05 14:04（JST 10/05 08:03〜10/05 23:04）
tier3候補 51件中 23件を選定（28件を件数上限により除外）
独立2媒体ペア救済: 4組（8件を上限外で追加）
収集窓: GMT 10/04 21:00〜10/05 21:00（JST 10/05 06:00〜10/06 06:00）（NY 17:00基準・半開区間）
取得上限（50件）に達した情報源: 日本銀行・Google News (Reuters検索)（上限を超える分は取得していないため、窓内の記事を取りこぼしている可能性があります）
候補の記録: outputs/2026-10-05/candidates_log.json（全111件の選定状態・公開時刻・呼び出しAの採否と理由）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS17・SKIP0・FAIL0）
  FAILしたチェックはありません。
向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告2件（向きの食い違い0・見出しのタグ0・指標日の見出し0・フロー書式2・媒体名照合0・地政学の不採用0）（ファイル先頭に表示）

月次累計（2026-10）: input=352403, output=50877（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
