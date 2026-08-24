#!/usr/bin/env python3
"""_diag_etf_source_verify.py — 一時的な調査用スクリプト。

オーナー指示によるFarside Investors・SoSoValueのETFフロー機械可読取得
可否の調査（並行research workflowの結果を実測で補強する）。

(1) Farside: 通常のHTTP GET（requestsライブラリ・既存のUSER_AGENT）で
    HTMLページに到達できるか、Cloudflare等のbot対策で弾かれるかを確認する。
    到達できても<table>のHTMLスクレイピングであり、既存のRSSベース
    アーキテクチャとは異質な実装が必要になる点は変わらない。
(2) SoSoValue: 開発者ポータル・APIドキュメントページに到達できるかを
    確認し、ETFフロー関連エンドポイントの実際のパスをドキュメントから
    読み取れるかを確認する（APIキーが無いため実際の呼び出しはできない）。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
import collect_news  # noqa: E402

PAGES = [
    ("Farside BTC", "https://farside.co.uk/btc/"),
    ("Farside ETH", "https://farside.co.uk/eth/"),
    ("Farside BTC全データ", "https://farside.co.uk/bitcoin-etf-flow-all-data/"),
    ("SoSoValue 開発者ポータル", "https://sosovalue.com/developer"),
    ("SoSoValue APIドキュメント", "https://sosovalue.gitbook.io/soso-value-api-doc"),
]


def main() -> None:
    for label, url in PAGES:
        print(f"===== {label} ({url}) =====")
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
            print(f"  HTTP {resp.status_code}  Content-Type={resp.headers.get('Content-Type', '')!r}")
            print(f"  取得サイズ: {len(resp.text)}文字")
            if resp.status_code == 200:
                lower = resp.text.lower()
                print(f"  'cloudflare' 含む: {'cloudflare' in lower}")
                print(f"  'captcha' 含む: {'captcha' in lower}")
                print(f"  '<table' 含む: {'<table' in lower}")
                print(f"  'etf' 含む: {'etf' in lower}")
                # ドキュメントページはAPIエンドポイントのパスらしき文字列を軽く探索
                if "sosovalue" in url:
                    import re
                    paths = sorted(set(re.findall(r'/api/[A-Za-z0-9_/\-]+', resp.text)))
                    print(f"  '/api/...' 風パス: {paths[:20]}")
        except requests.RequestException as e:
            print(f"  取得失敗: {type(e).__name__}: {e}")
        print()


if __name__ == "__main__":
    main()
