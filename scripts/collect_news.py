#!/usr/bin/env python3
"""collect_news.py — ニュース候補の収集（v0.3 §4・§10 第2弾-4）。

CryptoPanic API で候補の母集団のみを取得する。記事本文を根拠にはしない
（統合運用基準 §2）— 一次情報の裏取りは generate_post.py の呼び出しA内で
web_search ツールが行う。CryptoPanicが取得不能でも本スクリプトは失敗させず、
source_status に反映したうえで空候補リストを出力する（呼び出しAはこの状態でも
web_searchのみで続行できる設計）。

CryptoPanic側の取得条件（台本 §11 未確定事項1）は本実装で以下のとおり確定した
（DESIGN_CHANGES.md 参照）:
  - エンドポイント: Developer API v2 `https://cryptopanic.com/api/{plan}/v2/posts/`
    （`plan` は環境変数 CRYPTOPANIC_PLAN、既定 "developer" = 無料プランのスラッグ）。
  - 通貨フィルタ（currencies=）は v2 での対応が未確認のため付与しない。
    候補の絞り込みは行わず、kind=news の一般フィードをそのまま候補として渡し、
    実際の採否判断は generate_post.py 側のLLMプロンプト（優先度1〜4の選定基準）に委ねる。
  - 件数上限: 1ページ目の結果を先頭から最大 NEWS_LIMIT 件に切り詰める。

CLI:
  python scripts/collect_news.py <対象日 YYYY-MM-DD>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

CRYPTOPANIC_URL_TMPL = "https://cryptopanic.com/api/{plan}/v2/posts/"
DEFAULT_PLAN = "developer"
NEWS_LIMIT = 40
REQUEST_TIMEOUT_SEC = 15
JST = timezone(timedelta(hours=9))


def _now_jst_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _extract_candidate(item: dict) -> dict[str, str] | None:
    """CryptoPanicの1件をv0.3 §4.2の候補スキーマへ変換する。
    スキーマ不明・欠損に備えてすべて .get() 経由で読み、必須(title/url)が
    両方欠けている場合のみ捨てる（レスポンス形状の変化に対して寛容にする）。
    """
    if not isinstance(item, dict):
        return None
    title = item.get("title") or ""
    url = item.get("original_url") or item.get("url") or ""
    if not title and not url:
        return None
    source_obj = item.get("source")
    if isinstance(source_obj, dict):
        source = source_obj.get("title") or source_obj.get("domain") or ""
    else:
        source = item.get("domain") or ""
    return {
        "title": str(title),
        "url": str(url),
        "source": str(source),
        "published_at": str(item.get("published_at") or ""),
        "kind": str(item.get("kind") or "news"),
    }


def fetch_cryptopanic(api_key: str, plan: str = DEFAULT_PLAN) -> tuple[str, list[dict]]:
    """CryptoPanicから候補を取得する。

    戻り値: (source_status: "ok"|"failed", candidates)。
    ネットワーク障害・非200・JSON不正・想定外スキーマのいずれでも例外を送出せず
    "failed" を返す — 呼び出し側を止めないという§4.1の要件をここで担保する。
    """
    if not api_key:
        return "failed", []
    url = CRYPTOPANIC_URL_TMPL.format(plan=plan)
    try:
        resp = requests.get(
            url,
            params={"auth_token": api_key, "kind": "news"},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        if resp.status_code != 200:
            print(f"WARN: CryptoPanic HTTP {resp.status_code}", file=sys.stderr)
            return "failed", []
        body = resp.json()
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            print("WARN: CryptoPanic レスポンスに results 配列がありません", file=sys.stderr)
            return "failed", []
        candidates = []
        for item in results[:NEWS_LIMIT]:
            c = _extract_candidate(item)
            if c is not None:
                candidates.append(c)
        return "ok", candidates
    except requests.RequestException as e:
        print(f"WARN: CryptoPanic 取得失敗: {e}", file=sys.stderr)
        return "failed", []
    except (ValueError, TypeError) as e:  # JSON不正・想定外の型
        print(f"WARN: CryptoPanic レスポンス解析失敗: {e}", file=sys.stderr)
        return "failed", []


def collect_news(target_date: str, api_key: str, plan: str = DEFAULT_PLAN) -> dict[str, Any]:
    status, candidates = fetch_cryptopanic(api_key, plan)
    return {
        "collected_at": _now_jst_iso(),
        "target_date_jst": target_date,
        "source_status": {"cryptopanic": status, "count": len(candidates)},
        "candidates": candidates,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: collect_news.py <対象日 YYYY-MM-DD>", file=sys.stderr)
        return 1
    target_date = sys.argv[1]
    api_key = os.environ.get("CRYPTOPANIC_API_KEY", "")
    plan = os.environ.get("CRYPTOPANIC_PLAN", DEFAULT_PLAN)

    result = collect_news(target_date, api_key, plan)

    out_dir = Path(f"outputs/{target_date}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "news_candidates.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    status = result["source_status"]["cryptopanic"]
    count = result["source_status"]["count"]
    print(f"OK: {out_path}（cryptopanic={status}, count={count}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
