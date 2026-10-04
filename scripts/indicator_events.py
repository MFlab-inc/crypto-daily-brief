#!/usr/bin/env python3
"""indicator_events.py — 指標日（scheduled_eventsの重要度High・米国の経済指標）と、対応する材料・見出しの照合表（v1.93・オーナー承認）。

用途（2か所で同じ表を使う。表がずれて「目印は付くのに警告が出ない」等が起きないようにするため、1か所に集約した）:
  - generate_post.py: 呼び出しAへ渡す候補（当日の候補）に `scheduled_event_match`（その候補が当日のHigh米指標に
    対応する可能性があるという機械的な目印）を付ける。
  - verify_post.py: 指標日の見出しの警告（WARN）。指標に対応する材料が採用されているのに、見出しがその指標に触れていない日を示す。

照合はキーワード（正規表現）の一致で、意味の判定ではない。誤付与・見逃しが起こりうる（だから目印・警告にとどめ、
採否や本文の合否には使わない）。候補のタイトルは英語、見出しは日本語なので、指標ごとに英語（候補）と日本語（見出し）の
2種類の表を持つ。スケジュールの事実（カレンダー）自体が非公式JSON由来（collect_news.py）である点も限界。
"""
from __future__ import annotations

import re
from typing import Any

# key / label（日本語の指標名）/ event_re（カレンダーのtitle・英語）/ candidate_re（候補のtitle・英語）/ headline_re（見出し・日本語）
FAMILIES: tuple[dict[str, str], ...] = (
    {"key": "jobs", "label": "雇用統計",
     "event_re": r"Non-?Farm|Unemployment Rate|Average Hourly Earnings|Employment Change",
     "candidate_re": r"payrolls?|non-?farm|\bjobs\b|job growth|job gains|employment|unemployment|jobless",
     "headline_re": r"雇用統計|雇用者|非農業|失業率|雇用|賃金"},
    {"key": "cpi", "label": "CPI",
     "event_re": r"\bCPI\b",
     "candidate_re": r"\bCPI\b|consumer prices?|\binflation\b",
     "headline_re": r"CPI|消費者物価|インフレ|物価"},
    {"key": "ppi", "label": "PPI",
     "event_re": r"\bPPI\b",
     "candidate_re": r"\bPPI\b|producer prices?|wholesale prices?",
     "headline_re": r"PPI|生産者物価|卸売物価|物価"},
    {"key": "pce", "label": "PCE",
     "event_re": r"\bPCE\b",
     "candidate_re": r"\bPCE\b|personal consumption|\binflation\b",
     "headline_re": r"PCE|個人消費支出|物価|インフレ"},
    {"key": "gdp", "label": "GDP",
     "event_re": r"\bGDP\b",
     "candidate_re": r"\bGDP\b|gross domestic",
     "headline_re": r"GDP|国内総生産"},
    {"key": "fomc", "label": "FOMC",
     "event_re": r"FOMC|Federal Funds Rate|Fed Chair|Powell",
     "candidate_re": r"FOMC|\bFed\b.{0,20}\b(hike|hikes|hold|holds|raise|raises|cut|cuts|keep|keeps|rates?)\b"
                     r"|Federal Reserve.{0,40}\b(rates?|FOMC|hike|hikes|cut|cuts|holds?)\b|rate decision|Powell",
     "headline_re": r"FOMC|連邦公開市場|利上げ|利下げ|政策金利|金融政策|パウエル"},
    {"key": "ism", "label": "ISM",
     "event_re": r"\bISM\b",
     "candidate_re": r"\bISM\b|manufacturing PMI|factory activity|\bPMI\b",
     "headline_re": r"ISM|製造業|PMI"},
    {"key": "retail", "label": "小売売上高",
     "event_re": r"Retail Sales",
     "candidate_re": r"retail sales",
     "headline_re": r"小売売上"},
)


def high_us_event_families(scheduled_events: Any) -> list[dict[str, Any]]:
    """scheduled_eventsのうち、重要度High・米国（USD）の指標に当たる指標ファミリーを返す。
    各要素: {"family": FAMILIESの1件, "events": [カレンダーのtitle, ...]}。該当が無い・形式不正なら空リスト。"""
    out: list[dict[str, Any]] = []
    events = [e for e in (scheduled_events if isinstance(scheduled_events, list) else [])
              if isinstance(e, dict) and e.get("country") == "USD" and e.get("impact") == "High"
              and isinstance(e.get("title"), str)]
    for fam in FAMILIES:
        titles = [e["title"] for e in events if re.search(fam["event_re"], e["title"], re.I)]
        if titles:
            out.append({"family": fam, "events": titles})
    return out


def candidate_family_keys(title: Any, families: list[dict[str, Any]]) -> list[str]:
    """候補のtitle（英語）が対応しうる指標ファミリーのkey（families内のもの）。"""
    t = str(title or "")
    return [f["family"]["key"] for f in families if re.search(f["family"]["candidate_re"], t, re.I)]


def match_label(title: Any, families: list[dict[str, Any]]) -> str:
    """候補に付ける目印の文字列（例: 「雇用統計（Non-Farm Employment Change／Unemployment Rate）」）。対応が無ければ空文字列。
    複数の指標に対応しうる場合は「・」でつなぐ。"""
    keys = candidate_family_keys(title, families)
    parts = [f"{f['family']['label']}（{'／'.join(f['events'][:3])}）" for f in families if f["family"]["key"] in keys]
    return "・".join(parts)


def headline_mentions(headline: Any, family: dict[str, str]) -> bool:
    return bool(re.search(family["headline_re"], str(headline or "")))
