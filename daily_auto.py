#!/usr/bin/env python3
"""
데일리 테제 자동화 파이프라인 — 멀티 토픽 지원
TOPIC env: economy (경제·투자) | politics (정치) | culture (컬처)
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.parse
import html as _html
import hashlib
from datetime import datetime, timezone, timedelta

# ── 환경 변수 ─────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BOT_TOKEN         = os.environ.get("TELEGRAM_BOT_TOKEN", "")
def _resolve_topic():
    _VALID = ("economy", "economy_pm", "politics", "culture")
    # 1순위: 파일 큐 (_pending_topic.txt) — Railway가 economy_pm 등 세부 topic 지정 시 사용
    queue_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_pending_topic.txt")
    if os.path.exists(queue_file):
        try:
            with open(queue_file) as _f:
                queued = _f.read().strip().lower()
            os.remove(queue_file)
            if queued in _VALID:
                return queued
        except Exception:
            pass
    # 2순위: 환경변수 (daily.yml의 TOPIC env — 일반 스케줄 발행 시)
    env_t = os.environ.get("TOPIC", "").lower().strip()
    if env_t in _VALID:
        return env_t
    return "economy"

TOPIC             = _resolve_topic()
REPO_DIR          = os.path.dirname(os.path.abspath(__file__))
IS_CI             = os.environ.get("GITHUB_ACTIONS") == "true"
# ── 티스토리 블로그 환경 변수 ────────────────────────────────────
_TISTORY_ACCESS_TOKEN = os.environ.get("TISTORY_ACCESS_TOKEN", "")
_TISTORY_BLOG_NAME    = os.environ.get("TISTORY_BLOG_NAME", "")
_FRED_API_KEY         = os.environ.get("FRED_API_KEY", "")
_ECOS_API_KEY         = os.environ.get("ECOS_API_KEY", "")
_INDEXNOW_KEY         = os.environ.get("INDEXNOW_KEY", "")


KST      = timezone(timedelta(hours=9))
TODAY    = datetime.now(KST).strftime("%Y-%m-%d")
TODAY_KR = datetime.now(KST).strftime("%Y.%m.%d")

# ── 주제 설정 ─────────────────────────────────────────────────
TOPIC_CONFIG = {
    "economy": {
        "name": "경제·투자",
        "icon": "📊",
        "tags": ["매크로", "글로벌시장", "데일리테제"],
        "queries": [
            "글로벌 금융시장 오늘 뉴스 매크로",
            "Federal Reserve FOMC market news today",
            "미국 주식시장 경제지표 today",
        ],
        "channel_env": "TELEGRAM_CHANNEL_ECONOMY",
        "channel_id": "5066621346",
        "html_name": f"{TODAY}.html",
        "index_file": "index.html",
        "claude_instruction": (
            "오늘({today_kr}) 뉴스를 바탕으로 경제·투자 시장을 관통하는 핵심 테제 하나를 도출해줘.\n"
            "단순 뉴스 나열 금지. 하나의 테제로 오늘 시장을 설명해야 한다.\n"
            "투자자 관점에서 실질적으로 유용한 분석을 해줘."
        ),
        "index_title": "데일리 테제 — 경제·투자",
        "index_subtitle": "시장을 관통하는 하나의 테제 — by Jayce",
        "footer": "데일리 테제 분석 · 경제·투자 · 본 자료는 투자 권유가 아닙니다",
        "tg_hashtag": "#경제투자 #데일리테제",
    },
    "economy_pm": {
        "name": "경제·투자 (오후)",
        "icon": "📊",
        "tags": ["매크로", "오후마감", "글로벌시장", "데일리테제"],
        "queries": [
            "코스피 코스닥 오늘 마감 증시",
            "미국 증시 뉴욕 오늘 개장 전망",
            "달러 환율 원 오후 금리",
        ],
        "channel_env": "TELEGRAM_CHANNEL_ECONOMY",
        "channel_id": "5066621346",
        "html_name": f"{TODAY}-pm.html",
        "index_file": "index.html",
        "claude_instruction": (
            "오늘({today_kr}) 오후 기준으로 국내 증시 마감 흐름과 미국 시장 개장 전망을 바탕으로 "
            "경제·투자 핵심 테제 하나를 도출해줘.\n"
            "단순 뉴스 나열 금지. 오전 시황과 달라진 점·심화된 흐름에 주목해 "
            "오후 시장을 하나의 테제로 설명해야 한다.\n"
            "투자자가 오늘 저녁과 내일 포지션을 잡는 데 실질적으로 유용한 분석을 해줘."
        ),
        "index_title": "데일리 테제 — 경제·투자",
        "index_subtitle": "시장을 관통하는 하나의 테제 — by Jayce",
        "footer": "데일리 테제 분석 · 경제·투자 (오후) · 본 자료는 투자 권유가 아닙니다",
        "tg_hashtag": "#경제투자 #오후테제 #데일리테제",
    },
    "politics": {
        "name": "정치",
        "icon": "🏛️",
        "tags": ["한국정치", "글로벌정치", "데일리테제"],
        "queries": [
            "한국 정치 뉴스 오늘 국회 대통령",
            "Korea politics government policy news",
            "global politics international relations today",
        ],
        "channel_env": "TELEGRAM_CHANNEL_POLITICS",
        "channel_id": "5066621346",
        "html_name": f"{TODAY}-politics.html",
        "index_file": "politics.html",
        "claude_instruction": (
            "오늘({today_kr}) 뉴스를 바탕으로 정치 영역의 핵심 테제 하나를 도출해줘.\n"
            "한국 정치 60% + 글로벌 정치 40% 비중으로 다뤄야 한다.\n"
            "권력 구조, 정책 변화, 국제 관계의 흐름을 하나의 테제로 꿰어줘.\n"
            "편향 없이 사실 중심으로 분석하되, 실질적 영향을 중심으로 서술해줘."
        ),
        "index_title": "데일리 테제 — 정치",
        "index_subtitle": "오늘의 정치 흐름을 꿰는 하나의 테제 — by Jayce",
        "footer": "데일리 테제 분석 · 정치 · 사실에 근거한 중립적 분석입니다",
        "tg_hashtag": "#정치 #데일리테제",
    },
    "culture": {
        "name": "컬처",
        "icon": "🎬",
        "tags": ["한국문화", "글로벌트렌드", "데일리테제"],
        "queries": [
            "한국 문화 연예 트렌드 오늘 K-pop",
            "K-drama 한국 영화 뉴스",
            "global culture trends entertainment today",
        ],
        "channel_env": "TELEGRAM_CHANNEL_CULTURE",
        "channel_id": "5066621346",
        "html_name": f"{TODAY}-culture.html",
        "index_file": "culture.html",
        "claude_instruction": (
            "오늘({today_kr}) 뉴스를 바탕으로 문화·트렌드 영역의 핵심 테제 하나를 도출해줘.\n"
            "한국 문화/연예 60% + 글로벌 트렌드 40% 비중으로 다뤄야 한다.\n"
            "지금 가장 주목해야 할 문화적 흐름을 하나의 테제로 제시해줘.\n"
            "MZ 세대·팝컬처·콘텐츠 산업 관점에서 실질적 의미를 분석해줘."
        ),
        "index_title": "데일리 테제 — 컬처",
        "index_subtitle": "오늘의 문화 흐름을 읽는 하나의 테제 — by Jayce",
        "footer": "데일리 테제 분석 · 컬처 · 트렌드를 읽는 일상의 시각",
        "tg_hashtag": "#컬처 #데일리테제",
    },
}

def log(msg):
    print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] [{TOPIC.upper()}] {msg}", flush=True)

# ── 신뢰 RSS 소스 (직접 URL 제공 → 본문 크롤링 가능) ────────
_DIRECT_RSS = {
    "economy": [
        ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml",  6),
        ("연합뉴스 국제", "https://www.yna.co.kr/rss/international.xml", 3),
        ("CNBC Markets",  "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", 5),
        ("CNBC Economy",  "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", 4),
    ],
    "economy_pm": [
        ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml",  6),
        ("연합뉴스 국제", "https://www.yna.co.kr/rss/international.xml", 3),
        ("CNBC Markets",  "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", 5),
        ("CNBC Economy",  "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", 4),
    ],
    "politics": [
        ("연합뉴스 정치", "https://www.yna.co.kr/rss/politics.xml",    6),
        ("연합뉴스 국제", "https://www.yna.co.kr/rss/international.xml", 5),
        ("CNBC Politics", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000113", 4),
    ],
    "culture": [
        ("연합뉴스 문화", "https://www.yna.co.kr/rss/culture.xml",      6),
        ("연합뉴스 연예", "https://www.yna.co.kr/rss/entertainment.xml", 5),
    ],
}

_BOT_UA = "JAYCE-ThesisBot/1.0 (+https://jayce0321.github.io/daily-thesis)"

_CRAWL_HEADERS = {
    "User-Agent": _BOT_UA,
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _parse_direct_rss(rss_url, limit):
    """직접 URL RSS 파싱 → [{title, url, desc}] 반환.
    RSS 피드가 명시적으로 제공하는 description만 사용 (본문 크롤링 없음).
    """
    import re as _re
    results = []
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": _BOT_UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8", errors="replace")
        items = _re.findall(r'<item>(.*?)</item>', raw, _re.DOTALL)
        for item in items:
            t = _re.search(
                r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>',
                item, _re.DOTALL)
            if not t:
                continue
            title = t.group(1).strip()
            url = ""
            for pat in [r'<link>([^<]+)</link>',
                        r'<link[^>]+href=["\']([^"\']+)["\']',
                        r'<guid[^>]*>([^<]+)</guid>']:
                m = _re.search(pat, item)
                if m and m.group(1).strip().startswith("http"):
                    url = m.group(1).strip()
                    break
            # RSS 피드가 제공하는 description (저작권 문제 없는 공개 데이터)
            d = _re.search(
                r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>',
                item, _re.DOTALL)
            desc = ""
            if d:
                desc = _re.sub(r'<[^>]+>', '', d.group(1)).strip()[:200]
            results.append({"title": title, "url": url, "desc": desc})
            if len(results) >= limit:
                break
    except Exception as e:
        log(f"  직접 RSS 오류: {e}")
    return results


# ── 1. 뉴스 수집 ─────────────────────────────────────────────
def fetch_news(cfg):
    """RSS 피드 공개 데이터만 수집 (기사 본문 크롤링 없음).
    반환: (articles, source_log)
      articles   — [{title, url, desc}] 최대 28건
      source_log — [(source_name, count), ...] 출처별 건수
    """
    log("뉴스 수집 중...")
    import re as _re

    seen = set()
    articles   = []
    source_log = []   # (source_name, count)

    # ① 신뢰 RSS (언론사가 직접 배포하는 피드 — 제목+description 사용)
    topic_key = TOPIC
    for source_name, rss_url, limit in _DIRECT_RSS.get(topic_key, []):
        items = _parse_direct_rss(rss_url, limit)
        added = 0
        for art in items:
            if art["title"] in seen or len(art["title"]) < 6:
                continue
            seen.add(art["title"])
            articles.append(art)
            added += 1
        if added:
            source_log.append((source_name, added))
        log(f"  [{source_name}] {added}건")

    desc_count = sum(1 for a in articles if a.get("desc"))
    log(f"  → RSS description 확보: {desc_count}/{len(articles)}건")

    # ② Google News RSS (토픽별 쿼리 → 제목+desc 보완)
    topic_queries = cfg.get("queries", [])
    common_queries = [
        ("글로벌 금융시장 매크로 경제 오늘", "ko"),
        ("Federal Reserve interest rate economy today", "en"),
    ]
    all_queries = [(q, "ko") for q in topic_queries] + common_queries

    gnews_added = 0
    for q, lang in all_queries:
        try:
            encoded = urllib.parse.quote(q)
            if lang == "en":
                rss_url = (f"https://news.google.com/rss/search"
                           f"?q={encoded}&hl=en&gl=US&ceid=US:en")
            else:
                rss_url = (f"https://news.google.com/rss/search"
                           f"?q={encoded}&hl=ko&gl=KR&ceid=KR:ko")
            req = urllib.request.Request(rss_url, headers={"User-Agent": _BOT_UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read().decode("utf-8")

            items = _re.findall(r'<item>(.*?)</item>', raw, _re.DOTALL)
            for item in items[:6]:
                t_m = _re.search(
                    r'<title><!\[CDATA\[(.*?)\]\]></title>', item)
                if not t_m:
                    t_m = _re.search(r'<title>(.*?)</title>', item)
                d_m = _re.search(
                    r'<description><!\[CDATA\[(.*?)\]\]></description>', item)
                if not d_m:
                    d_m = _re.search(
                        r'<description>(.*?)</description>', item)
                if t_m:
                    title = t_m.group(1).strip()
                    title = _re.sub(r'\s*-\s*[^-]{2,30}$', '', title).strip()
                    if title in seen or len(title) < 8:
                        continue
                    seen.add(title)
                    desc = ""
                    if d_m:
                        desc = _re.sub(
                            r'<[^>]+>', '', d_m.group(1)).strip()[:120]
                    articles.append({"title": title, "url": "", "desc": desc})
                    gnews_added += 1
        except Exception as e:
            log(f"  [{q[:18]}] 수집 오류: {e}")

    if gnews_added:
        source_log.append(("Google News", gnews_added))

    log(f"뉴스 총 {len(articles)}건 수집 완료 (소스 {len(source_log)}개)")
    return articles[:28], source_log


def fetch_live_data():
    """FRED + ECOS 공개 API에서 실시간 경제 수치 수집 (API 키 없으면 빈 리스트 반환)"""
    results = []

    def _get(url, label):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _BOT_UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            log(f"  live_data 스킵 ({label}): {e}")
            return None

    if _FRED_API_KEY:
        base = "https://api.stlouisfed.org/fred/series/observations"
        params = f"&file_type=json&limit=1&sort_order=desc&api_key={_FRED_API_KEY}"
        for series, label in [("DGS10", "미 10년 국채"), ("EFFR", "연방기금금리"), ("DEXKOUS", "원달러 환율")]:
            d = _get(f"{base}?series_id={series}{params}", label)
            if d:
                obs = (d.get("observations") or [{}])[-1]
                val = obs.get("value", ".")
                if val != ".":
                    results.append(f"{label}: {val} ({obs.get('date','')})")

    if _ECOS_API_KEY:
        # 한국은행 기준금리 (722Y001 / 0101000)
        ym = TODAY.replace("-", "")
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{_ECOS_API_KEY}"
            f"/json/kr/1/1/722Y001/D/{ym[:6]}01/{ym[:6]}31/0101000"
        )
        d = _get(url, "ECOS 기준금리")
        if d:
            rows = d.get("StatisticSearch", {}).get("row", [])
            if rows:
                r = rows[-1]
                results.append(f"한국 기준금리: {r.get('DATA_VALUE','?')}% ({r.get('TIME','?')})")

    if results:
        log(f"실시간 데이터 {len(results)}개 수집: {', '.join(results)}")
    return results


def call_claude(news_headlines, cfg, live_data=None):
    log("Claude API 호출 중...")
    parts = []
    for i, a in enumerate(news_headlines):
        if isinstance(a, dict):
            title = a.get("title", "")
            body  = a.get("body", "")
            desc  = a.get("desc", "")
            if body:
                parts.append(f"[{i+1}] {title}\n    본문: {body}")
            elif desc:
                parts.append(f"[{i+1}] {title}\n    요약: {desc}")
            else:
                parts.append(f"[{i+1}] {title}")
        else:
            parts.append(f"[{i+1}] {a}")
    headlines_text = "\n\n".join(parts)

    instruction = cfg["claude_instruction"].format(today_kr=TODAY_KR)
    # RSS description이 있는 기사는 수치 신뢰도 강조
    desc_count = sum(1 for a in news_headlines
                     if isinstance(a, dict) and a.get("desc"))
    if desc_count > 0:
        instruction += (
            f"\n\n※ {desc_count}개 기사는 RSS 요약문이 포함되어 있습니다. "
            "metrics의 수치는 반드시 기사 정보에서 확인된 것만 사용하고, "
            "없으면 '확인 필요'로 표기하세요."
        )

    tool_def = {
        "name": "save_thesis",
        "description": "데일리 테제 분석 결과를 저장한다",
        "input_schema": {
            "type": "object",
            "properties": {
                "thesis_title": {"type": "string", "description": "테제 제목 (따옴표 포함, 20자 내외)"},
                "one_line":     {"type": "string", "description": "한 줄 핵심 요약"},
                "why_important":{"type": "string", "description": "왜 중요한가 (배경 설명 2~3문장)"},
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label":   {"type": "string"},
                            "value":   {"type": "string"},
                            "meaning": {"type": "string"}
                        },
                        "required": ["label", "value", "meaning"]
                    },
                    "description": "숫자 근거 3~4개"
                },
                "scenario_a": {
                    "type": "object",
                    "properties": {
                        "title":  {"type": "string"},
                        "points": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["title", "points"]
                },
                "scenario_b": {
                    "type": "object",
                    "properties": {
                        "title":  {"type": "string"},
                        "points": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["title", "points"]
                },
                "checklist": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "desc":  {"type": "string"}
                        },
                        "required": ["title", "desc"]
                    },
                    "description": "체크리스트 2~3개"
                },
                "closing": {"type": "string", "description": "마무리 한 줄"},
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "분석 확신도 — high: 뉴스 10건+ 수치 검증 완료, medium: 5~9건 일부 추정, low: 5건 미만 정보 제한적"
                },
                "watch_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date":  {"type": "string", "description": "날짜 또는 '이번 주', '다음 주', '~일' 등"},
                            "event": {"type": "string", "description": "이벤트명 (예: FOMC 회의, 미 CPI 발표)"},
                            "why":   {"type": "string", "description": "왜 주목해야 하는가 (1줄)"}
                        },
                        "required": ["date", "event", "why"]
                    },
                    "description": "다음으로 주목할 이벤트 2~3개 (FOMC·경제지표·국회일정 등)"
                }
            },
            "required": ["thesis_title", "one_line", "why_important", "metrics",
                         "scenario_a", "scenario_b", "checklist", "closing",
                         "confidence", "watch_list"]
        }
    }

    data = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 2800,
        "tools": [tool_def],
        "tool_choice": {"type": "tool", "name": "save_thesis"},
        "messages": [{
            "role": "user",
            "content": (
            f"{instruction}\n\n수집된 뉴스:\n{headlines_text}"
            + (f"\n\n실시간 공식 경제 수치 (FRED/ECOS API):\n" + "\n".join(live_data) if live_data else "")
        )
        }]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        result = json.loads(r.read().decode("utf-8"))

    for block in result["content"]:
        if block.get("type") == "tool_use":
            log("Claude 분석 완료")
            return block["input"]

    raise ValueError(f"tool_use 응답 없음: {result}")

# ── 2b. SVG 생성 ──────────────────────────────────────────────
def generate_svgs(analysis):
    log("SVG 생성 중...")
    metrics  = analysis.get("metrics", [])
    title    = analysis.get("thesis_title", "")

    seed = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
    cx1, cy1 = 650 + (seed % 80), 80 + (seed % 60)
    cx2, cy2 = 750 + (seed % 50), 200 + (seed % 80)
    cx3, cy3 = 500 + (seed % 100), 300 + (seed % 60)

    cover_svg = f'''<svg viewBox="0 0 900 360" xmlns="http://www.w3.org/2000/svg" font-family="'Apple SD Gothic Neo','Noto Sans KR',sans-serif">
  <defs>
    <radialGradient id="bg" cx="70%" cy="30%" r="80%">
      <stop offset="0%" stop-color="#0d2040"/>
      <stop offset="100%" stop-color="#0d0f14"/>
    </radialGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="18"/></filter>
  </defs>
  <rect width="900" height="360" fill="url(#bg)"/>
  <circle cx="{cx1}" cy="{cy1}" r="160" fill="#1a3a5c" filter="url(#blur)" opacity="0.6"/>
  <circle cx="{cx2}" cy="{cy2}" r="120" fill="#1a2a10" filter="url(#blur)" opacity="0.4"/>
  <circle cx="{cx1}" cy="{cy1}" r="90" fill="none" stroke="#e8b84b" stroke-width="1" opacity="0.25"/>
  <circle cx="{cx1}" cy="{cy1}" r="50" fill="none" stroke="#e8b84b" stroke-width="0.5" opacity="0.4"/>
  <circle cx="{cx2}" cy="{cy2}" r="70" fill="none" stroke="#5b8dee" stroke-width="1" opacity="0.3"/>
  <circle cx="{cx3}" cy="{cy3}" r="40" fill="#e8b84b" opacity="0.06"/>
  <line x1="{cx1-100}" y1="{cy1+30}" x2="{cx2+50}" y2="{cy2-40}" stroke="#e8b84b" stroke-width="0.5" opacity="0.2"/>
  <line x1="0" y1="310" x2="900" y2="310" stroke="#252b3b" stroke-width="1"/>
  <text x="870" y="32" text-anchor="end" fill="#4a5269" font-size="12" letter-spacing="1">{TODAY_KR}</text>
</svg>'''

    colors  = ["#e05c5c", "#e8b84b", "#5b8dee", "#4caf80", "#a78bfa"]
    bar_h   = 32
    gap     = 16
    pad_top = 40
    pad_l   = 210
    max_bar = 500
    chart_h = pad_top + len(metrics) * (bar_h + gap) + 30

    bars = ""
    for i, m in enumerate(metrics):
        y   = pad_top + i * (bar_h + gap)
        col = colors[i % len(colors)]
        w   = max(60, max_bar - i * (max_bar // max(len(metrics), 1) // 2 + 40))
        lbl = _html.escape(m.get("label", "")[:22])
        val = _html.escape(m.get("value", ""))
        bars += f'''  <text x="{pad_l - 10}" y="{y + bar_h//2 + 5}" text-anchor="end" fill="#7a8299" font-size="12">{lbl}</text>
  <rect x="{pad_l}" y="{y}" width="{w}" height="{bar_h}" fill="{col}" rx="4" opacity="0.85"/>
  <text x="{pad_l + w + 8}" y="{y + bar_h//2 + 5}" fill="#e2e6f0" font-size="13" font-weight="700">{val}</text>\n'''

    chart_svg = f'''<svg viewBox="0 0 800 {chart_h}" xmlns="http://www.w3.org/2000/svg" font-family="'Apple SD Gothic Neo','Noto Sans KR',sans-serif">
  <rect width="800" height="{chart_h}" fill="#161a23"/>
  <text x="20" y="26" fill="#4a5269" font-size="11" letter-spacing="2">KEY METRICS</text>
{bars}</svg>'''

    return cover_svg, chart_svg

# ── 3. HTML 생성 ─────────────────────────────────────────────
def _safe(val):
    return _html.escape(str(val)) if val is not None else ""

_PAGES_URL = "https://jayce0321.github.io/daily-thesis"

def _update_feed(analysis, cfg, page_url):
    """RSS 2.0 피드 업데이트.
    - CDATA로 특수문자 안전 처리 (XML 인젝션 방지)
    - description은 요약 텍스트만 포함 (민감정보 제외)
    - 최대 30개 아이템 유지
    """
    import re as _re
    from email.utils import formatdate
    import time as _time

    feed_path = os.path.join(REPO_DIR, "feed.xml")

    # 기존 피드에서 아이템 추출 (최대 29개 보존)
    existing_items, existing_guids = [], set()
    if os.path.exists(feed_path):
        with open(feed_path, "r", encoding="utf-8") as _f:
            _raw = _f.read()
        for _item in _re.findall(r'<item>.*?</item>', _raw, _re.DOTALL):
            _g = _re.search(r'<guid[^>]*>(.*?)</guid>', _item)
            if _g:
                existing_guids.add(_g.group(1))
            existing_items.append(_item)
    existing_items = existing_items[:29]

    items_xml = ""
    if page_url not in existing_guids:
        _title_raw   = f"{cfg['icon']} {cfg['name']} 데일리 테제 | {TODAY_KR}"
        _desc_raw    = (
            f"{analysis.get('thesis_title','').strip()} — "
            f"{analysis.get('one_line','').strip()}"
        )[:200]
        items_xml = (
            "  <item>\n"
            f"    <title><![CDATA[{_title_raw}]]></title>\n"
            f"    <link>{page_url}</link>\n"
            f"    <description><![CDATA[{_desc_raw}]]></description>\n"
            f"    <pubDate>{formatdate(_time.time())}</pubDate>\n"
            f"    <guid isPermaLink=\"true\">{page_url}</guid>\n"
            f"    <category><![CDATA[{cfg['name']}]]></category>\n"
            "  </item>\n"
        )
    for _i in existing_items:
        items_xml += _i + "\n"

    feed_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"\n'
        '  xmlns:atom="http://www.w3.org/2005/Atom"\n'
        '  xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <channel>\n"
        "    <title>JAYCE 데일리 테제</title>\n"
        f"    <link>{_PAGES_URL}</link>\n"
        "    <description>경제·투자·정치·컬처 — 시장을 관통하는 하나의 테제 by Jayce</description>\n"
        "    <language>ko</language>\n"
        f"    <lastBuildDate>{formatdate(_time.time())}</lastBuildDate>\n"
        "    <ttl>60</ttl>\n"
        f"    <atom:link href=\"{_PAGES_URL}/feed.xml\" rel=\"self\" type=\"application/rss+xml\"/>\n"
        f"{items_xml}"
        "  </channel>\n"
        "</rss>"
    )
    with open(feed_path, "w", encoding="utf-8") as _f:
        _f.write(feed_xml)
    log("RSS feed.xml 업데이트")
    return feed_path


def _update_sitemap():
    """sitemap.xml 업데이트.
    - URL은 html.escape()로 안전 처리
    - 인덱스 페이지 + 전체 아티클 포함
    """
    import re as _re

    sitemap_path = os.path.join(REPO_DIR, "sitemap.xml")
    skip = {"404.html"}
    index_pages = {"index.html", "politics.html", "culture.html"}

    html_files = sorted(
        [f for f in os.listdir(REPO_DIR)
         if f.endswith(".html") and f not in skip],
        reverse=True,
    )

    url_entries = []
    # 인덱스 페이지
    for idx in ["index.html", "politics.html", "culture.html"]:
        if os.path.exists(os.path.join(REPO_DIR, idx)):
            priority = "1.0" if idx == "index.html" else "0.9"
            url_entries.append(
                f"  <url>\n"
                f"    <loc>{_PAGES_URL}/{_html.escape(idx)}</loc>\n"
                f"    <changefreq>daily</changefreq>\n"
                f"    <priority>{priority}</priority>\n"
                f"    <lastmod>{TODAY}</lastmod>\n"
                f"  </url>"
            )
    # 아티클 페이지
    for f in html_files:
        if f in index_pages:
            continue
        date_m = _re.match(r'(\d{4}-\d{2}-\d{2})', f)
        lastmod = date_m.group(1) if date_m else TODAY
        url_entries.append(
            f"  <url>\n"
            f"    <loc>{_PAGES_URL}/{_html.escape(f)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>never</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"  </url>"
        )

    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(url_entries)
        + "\n</urlset>"
    )
    with open(sitemap_path, "w", encoding="utf-8") as _f:
        _f.write(sitemap_xml)
    log("sitemap.xml 업데이트")
    return sitemap_path

# ── 티스토리 블로그 통합 ─────────────────────────────────────────
def _tistory_blog_html(analysis: dict, cfg: dict, page_url: str) -> str:
    """티스토리 블로그용 HTML 본문 생성 (body 내용만).
    - 인라인 스타일로 티스토리 테마와 충돌 방지
    - 모든 사용자 데이터 html.escape() 처리 (XSS 방지)
    """
    def esc(v):
        return _html.escape(str(v)) if v else ""

    thesis  = esc(analysis.get("thesis_title", ""))
    one_ln  = esc(analysis.get("one_line", ""))
    why     = esc(analysis.get("why_important", ""))
    closing = esc(analysis.get("closing", analysis.get("one_line", "")))
    metrics = analysis.get("metrics", [])
    sa = analysis.get("scenario_a", {})
    sb = analysis.get("scenario_b", {})
    checklist = analysis.get("checklist", [])
    if isinstance(sa, str): sa = {"title": sa, "points": []}
    if isinstance(sb, str): sb = {"title": sb, "points": []}
    if not isinstance(sa, dict): sa = {}
    if not isinstance(sb, dict): sb = {}

    # 메트릭 테이블
    rows = "".join(
        f"<tr><td style='padding:8px 12px;border:1px solid #ddd;'><b>{esc(m.get('label',''))}</b></td>"
        f"<td style='padding:8px 12px;border:1px solid #ddd;font-weight:700;'>{esc(m.get('value',''))}</td>"
        f"<td style='padding:8px 12px;border:1px solid #ddd;color:#555;'>{esc(m.get('meaning',''))}</td></tr>"
        for m in metrics if isinstance(m, dict)
    )
    metrics_html = (
        "<table style='width:100%;border-collapse:collapse;margin:12px 0;font-size:14px;'>"
        "<thead><tr style='background:#f8f8f8;'>"
        "<th style='padding:8px 12px;border:1px solid #ddd;text-align:left;'>지표</th>"
        "<th style='padding:8px 12px;border:1px solid #ddd;text-align:left;'>수치</th>"
        "<th style='padding:8px 12px;border:1px solid #ddd;text-align:left;'>의미</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    ) if rows else ""

    sa_pts = "".join(f"<li style='margin:4px 0;color:#333;'>{esc(p)}</li>" for p in sa.get("points", []))
    sb_pts = "".join(f"<li style='margin:4px 0;color:#333;'>{esc(p)}</li>" for p in sb.get("points", []))
    _cl_parts = []
    for c in checklist:
        _t = esc(c.get("title", "") if isinstance(c, dict) else c)
        _d = (' — <span style="color:#666;font-size:13px;">' + esc(c["desc"]) + "</span>") if isinstance(c, dict) and c.get("desc") else ""
        _cl_parts.append(f"<li style='margin:6px 0;'><b>{_t}</b>{_d}</li>")
    cl_items = "".join(_cl_parts)

    page_url_esc  = _html.escape(page_url)
    pages_url_esc = _html.escape(_PAGES_URL)

    return (
        f"<div style='background:#f0f4ff;border-left:4px solid #2367d7;padding:16px 20px;margin:0 0 24px;border-radius:4px;'>"
        f"<p style='margin:0;font-size:13px;color:#666;'>{cfg['icon']} {cfg['name']} 데일리 테제 | {TODAY_KR}</p>"
        f"<p style='margin:4px 0 0;font-size:12px;color:#999;'>※ <a href='{page_url_esc}' target='_blank'>JAYCE 데일리 테제</a>에서 자동 발행됩니다.</p>"
        f"</div>"
        f"<h2 style='font-size:22px;margin:0 0 12px;line-height:1.4;'>{thesis}</h2>"
        f"<p style='font-size:16px;color:#333;line-height:1.7;margin:0 0 28px;padding:16px;background:#fafafa;border-radius:4px;'>{one_ln}</p>"
        f"<h3 style='font-size:16px;border-bottom:2px solid #2367d7;padding-bottom:8px;margin:28px 0 12px;'>왜 이게 중요한가</h3>"
        f"<p style='font-size:15px;color:#333;line-height:1.8;'>{why}</p>"
        f"<h3 style='font-size:16px;border-bottom:2px solid #2367d7;padding-bottom:8px;margin:28px 0 12px;'>숫자로 보는 근거</h3>"
        f"{metrics_html}"
        f"<h3 style='font-size:16px;border-bottom:2px solid #2367d7;padding-bottom:8px;margin:28px 0 12px;'>시나리오 분기</h3>"
        f"<div style='display:flex;gap:16px;margin:12px 0;'>"
        f"<div style='flex:1;border:1px solid #ddd;border-top:3px solid #4caf80;border-radius:4px;padding:16px;'>"
        f"<p style='margin:0 0 8px;font-size:11px;font-weight:700;color:#4caf80;text-transform:uppercase;letter-spacing:.05em;'>시나리오 A</p>"
        f"<h4 style='margin:0 0 8px;font-size:14px;'>{esc(sa.get('title',''))}</h4>"
        f"<ul style='margin:0;padding-left:16px;'>{sa_pts}</ul></div>"
        f"<div style='flex:1;border:1px solid #ddd;border-top:3px solid #e05c5c;border-radius:4px;padding:16px;'>"
        f"<p style='margin:0 0 8px;font-size:11px;font-weight:700;color:#e05c5c;text-transform:uppercase;letter-spacing:.05em;'>시나리오 B</p>"
        f"<h4 style='margin:0 0 8px;font-size:14px;'>{esc(sb.get('title',''))}</h4>"
        f"<ul style='margin:0;padding-left:16px;'>{sb_pts}</ul></div>"
        f"</div>"
        f"<h3 style='font-size:16px;border-bottom:2px solid #2367d7;padding-bottom:8px;margin:28px 0 12px;'>체크리스트</h3>"
        f"<ul style='margin:0;padding-left:20px;'>{cl_items}</ul>"
        f"<blockquote style='border-left:3px solid #ccc;margin:24px 0;padding:12px 20px;color:#555;font-style:italic;'>"
        f"<p style='margin:0;'>{closing}</p></blockquote>"
        f"<p style='margin:24px 0 8px;'>"
        f"🔗 <a href='{page_url_esc}' target='_blank' style='color:#2367d7;'>전체 분석 보기 (차트·상세 데이터 포함)</a></p>"
        f"<p style='margin:0;'><a href='{pages_url_esc}' target='_blank' style='color:#2367d7;'>JAYCE 데일리 테제 아카이브</a></p>"
        f"<p style='margin:16px 0 0;color:#888;font-size:13px;'>{cfg.get('tg_hashtag','')}</p>"
    )


def _post_to_tistory(analysis: dict, cfg: dict, page_url: str) -> bool:
    """티스토리 블로그에 포스팅.
    - Access Token은 만료 없음 (앱 삭제 전까지 유효)
    - 실패해도 예외를 올리지 않음 (텔레그램·GitHub 발행 이미 완료)
    """
    if not (_TISTORY_ACCESS_TOKEN and _TISTORY_BLOG_NAME):
        log("[TISTORY] 설정 없음 — 포스팅 스킵 (TISTORY_ACCESS_TOKEN/BLOG_NAME 설정 필요)")
        return False
    try:
        title_str = (
            f"{cfg['icon']} {cfg['name']} 데일리 테제 | {TODAY_KR}"
            f" — {analysis.get('thesis_title','')}"
        )
        contents = _tistory_blog_html(analysis, cfg, page_url)
        tags_str = ",".join(
            dict.fromkeys([t[:10] for t in cfg.get("tags", [])][:9] + ["데일리테제"])
        )

        body = urllib.parse.urlencode({
            "access_token": _TISTORY_ACCESS_TOKEN,
            "output":       "json",
            "blogName":     _TISTORY_BLOG_NAME,
            "title":        title_str,
            "content":      contents,
            "visibility":   "3",   # 3=공개, 0=비공개, 1=보호
            "tag":          tags_str,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://www.tistory.com/apis/post/write",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode("utf-8"))

        ts = resp.get("tistory", {})
        if str(ts.get("status")) == "200":
            post_url = ts.get("url", "")
            log(f"[TISTORY] 포스팅 완료: {post_url}")
            return True
        else:
            log(f"[TISTORY] 포스팅 실패: {resp}")
            return False
    except Exception as e:
        log(f"[TISTORY] 포스팅 오류 (무시): {e}")
        return False




# ── AEO/GEO 구조화 데이터 ────────────────────────────────────────
def _build_json_ld(a: dict, cfg: dict, page_url: str) -> str:
    """Article + FAQPage + BreadcrumbList JSON-LD 생성 (GEO-16 표준)"""
    thesis_title = a.get("thesis_title", "")
    one_line     = a.get("one_line", "")
    why          = a.get("why_important", "")
    metrics      = a.get("metrics", [])
    sa           = a.get("scenario_a", {}) or {}
    sb           = a.get("scenario_b", {}) or {}
    checklist    = a.get("checklist", [])
    if isinstance(sa, str): sa = {}
    if isinstance(sb, str): sb = {}

    faq_items = [{
        "@type": "Question",
        "name": f"오늘의 {cfg['name']} 핵심 테제는 무엇인가?",
        "acceptedAnswer": {"@type": "Answer", "text": one_line},
    }]
    if why:
        faq_items.append({
            "@type": "Question",
            "name": "왜 이 분석이 중요한가?",
            "acceptedAnswer": {"@type": "Answer", "text": why[:500]},
        })
    if metrics:
        m_text = " | ".join(
            f"{m.get('label','')}: {m.get('value','')} ({m.get('meaning','')})"
            for m in metrics[:4] if isinstance(m, dict)
        )
        faq_items.append({
            "@type": "Question",
            "name": "오늘의 핵심 지표와 수치는 무엇인가?",
            "acceptedAnswer": {"@type": "Answer", "text": m_text},
        })
    if isinstance(sa, dict) and sa.get("title"):
        pts = "; ".join(sa.get("points", [])[:2])
        faq_items.append({
            "@type": "Question",
            "name": "상승(긍정) 시나리오의 조건은 무엇인가?",
            "acceptedAnswer": {"@type": "Answer",
                               "text": sa["title"] + (f" — {pts}" if pts else "")},
        })
    if isinstance(sb, dict) and sb.get("title"):
        pts = "; ".join(sb.get("points", [])[:2])
        faq_items.append({
            "@type": "Question",
            "name": "하락(리스크) 시나리오의 위험 요인은 무엇인가?",
            "acceptedAnswer": {"@type": "Answer",
                               "text": sb["title"] + (f" — {pts}" if pts else "")},
        })
    for c in checklist[:2]:
        if isinstance(c, dict) and c.get("title") and c.get("desc"):
            faq_items.append({
                "@type": "Question",
                "name": f"{c['title']}을(를) 어떻게 확인해야 하나?",
                "acceptedAnswer": {"@type": "Answer", "text": c["desc"]},
            })

    article_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": thesis_title,
        "description": one_line[:160],
        "datePublished": TODAY,
        "dateModified": TODAY,
        "author": {"@type": "Person", "name": "Jayce"},
        "publisher": {"@type": "Organization", "name": "JAYCE 데일리 테제", "url": _PAGES_URL},
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        "about": [{"@type": "Thing", "name": t} for t in cfg.get("tags", [])],
        "speakable": {"@type": "SpeakableSpecification",
                      "cssSelector": ["#direct-answer", "#faq-section"]},
        "inLanguage": "ko",
    }
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_items}
    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1,
             "name": "JAYCE 데일리 테제", "item": _PAGES_URL},
            {"@type": "ListItem", "position": 2,
             "name": cfg["name"], "item": f"{_PAGES_URL}/{cfg['index_file']}"},
            {"@type": "ListItem", "position": 3,
             "name": thesis_title, "item": page_url},
        ],
    }

    def _ld(obj):
        return (f'<script type="application/ld+json">\n'
                f'{json.dumps(obj, ensure_ascii=False, indent=2)}\n'
                f'</script>')

    return "\n".join([_ld(article_ld), _ld(faq_ld), _ld(breadcrumb_ld)])


def _build_faq_html(a: dict, cfg: dict) -> str:
    """AEO/GEO 노출용 FAQ 섹션 HTML (AI 엔진 직접 인용 최적화)"""
    one_line  = a.get("one_line", "")
    why       = a.get("why_important", "")
    metrics   = a.get("metrics", [])
    sa        = a.get("scenario_a", {}) or {}
    sb        = a.get("scenario_b", {}) or {}
    checklist = a.get("checklist", [])
    if isinstance(sa, str): sa = {}
    if isinstance(sb, str): sb = {}

    faqs = [(f"오늘의 {cfg['name']} 핵심 테제는?", one_line)]
    if why:
        faqs.append(("왜 이 분석이 중요한가?", why[:250]))
    if metrics:
        m_text = " · ".join(
            f"{m.get('label','')}: {m.get('value','')}"
            for m in metrics[:3] if isinstance(m, dict)
        )
        faqs.append(("오늘의 핵심 수치는?", m_text))
    if isinstance(sa, dict) and sa.get("title"):
        pts = "; ".join(sa.get("points", [])[:2])
        faqs.append(("상승 시나리오는?",
                     sa["title"] + (f" — {pts}" if pts else "")))
    if isinstance(sb, dict) and sb.get("title"):
        pts = "; ".join(sb.get("points", [])[:2])
        faqs.append(("리스크 시나리오는?",
                     sb["title"] + (f" — {pts}" if pts else "")))
    for c in checklist[:2]:
        if isinstance(c, dict) and c.get("title") and c.get("desc"):
            faqs.append((f"{c['title']}은 왜 중요한가?", c["desc"]))

    items_html = "".join(
        f'<div class="faq-item">'
        f'<dt class="faq-q">{_safe(q)}</dt>'
        f'<dd class="faq-a">{_safe(ans)}</dd>'
        f'</div>'
        for q, ans in faqs
    )
    return (
        f'<div id="faq-section" class="section">\n'
        f'  <div class="section-header">'
        f'<div class="section-number">Q</div>'
        f'<h2>자주 묻는 질문</h2></div>\n'
        f'  <dl class="faq-list">{items_html}</dl>\n'
        f'</div>'
    )


def build_html(a, cfg, cover_svg="", chart_svg="", page_url="", source_log=None):
    if not page_url:
        page_url = f"https://jayce0321.github.io/daily-thesis/{cfg['html_name']}"
    _seo_desc = _safe(a.get("one_line", "")[:150])
    _seo_title = _safe(f"데일리 테제 | {cfg['name']} | {TODAY_KR}")
    _json_ld_scripts = _build_json_ld(a, cfg, page_url)
    _faq_html        = _build_faq_html(a, cfg)
    _seo_keywords    = _safe(", ".join(cfg["tags"] + [cfg["name"], "데일리테제", "Jayce"]))

    # ── 확신도 배너 ──────────────────────────────────────────────
    _confidence = a.get("confidence", "high")
    _confidence_banner = ""
    if _confidence == "medium":
        _confidence_banner = (
            '<div class="conf-banner medium">'
            '📊 오늘은 뉴스 정보가 <strong>보통 수준</strong>입니다 — 수치 해석에 유의하세요.</div>'
        )
    elif _confidence == "low":
        _confidence_banner = (
            '<div class="conf-banner low">'
            '⚠ 오늘은 뉴스 정보가 <strong>제한적</strong>입니다 — 테제는 참고용으로만 활용하세요.</div>'
        )

    # ── Watch List ───────────────────────────────────────────────
    _watch_rows = "".join(
        '<div class="watch-item">'
        f'<span class="watch-date">{_safe(w.get("date",""))}</span>'
        '<div class="watch-main">'
        f'<span class="watch-event">{_safe(w.get("event",""))}</span>'
        f'<span class="watch-why">{_safe(w.get("why",""))}</span>'
        '</div></div>'
        for w in a.get("watch_list", []) if isinstance(w, dict)
    )
    _watch_html = (
        '<div class="section" id="watch-list">'
        '<div class="section-header">'
        '<div class="section-number" style="background:var(--accent2)">5</div>'
        '<h2>Watch List — 다음 주목 포인트</h2></div>'
        f'<div class="watch-list-wrap">{_watch_rows}</div>'
        '</div>'
    ) if _watch_rows else ""

    # ── 읽기 시간 ────────────────────────────────────────────────
    _char_count = sum(len(str(v)) for v in [
        a.get("why_important", ""), a.get("one_line", ""), a.get("closing", ""),
        " ".join(m.get("meaning", "") for m in a.get("metrics", []) if isinstance(m, dict)),
    ])
    _read_min = max(1, round(_char_count / 400))

    # ── 소셜 공유 버튼 ───────────────────────────────────────────
    _enc_url   = urllib.parse.quote(page_url, safe="")
    _enc_title = urllib.parse.quote(
        f"데일리 테제 | {_safe(a.get('thesis_title',''))} | {TODAY_KR}", safe="")
    _share_html = (
        '<div class="share-row">'
        '<span class="share-label">공유</span>'
        f'<a class="share-btn" href="https://twitter.com/intent/tweet?url={_enc_url}&text={_enc_title}"'
        ' target="_blank" rel="noopener">𝕏 공유</a>'
        '<button class="share-btn" id="share-native-btn"'
        ' onclick="shareNative()" style="display:none">공유하기</button>'
        '</div>'
    )

    # ── 교차 링크 (오늘의 다른 테제) ────────────────────────────
    _cross_topics = [
        ("경제·투자", f"{TODAY}.html", "📊"),
        ("정치", f"{TODAY}-politics.html", "🏛️"),
        ("컬처", f"{TODAY}-culture.html", "🎬"),
        ("경제 (오후)", f"{TODAY}-pm.html", "📊"),
    ]
    _cross_cards = "".join(
        f'<a class="cross-card" href="{fname}">{icon} {name}</a>'
        for name, fname, icon in _cross_topics
        if fname != cfg["html_name"]
    )
    _cross_html = (
        '<div class="cross-section">'
        '<div class="cross-label">오늘의 다른 테제</div>'
        f'<div class="cross-grid">{_cross_cards}</div>'
        '</div>'
    ) if _cross_cards else ""

    # ── 추가 CSS ─────────────────────────────────────────────────
    _extra_css = (
        ".conf-banner{display:flex;align-items:flex-start;gap:10px;border-radius:6px;"
        "padding:12px 18px;margin-bottom:24px;font-size:13px;line-height:1.6;}"
        ".conf-banner.medium{background:rgba(232,150,58,.07);border:1px solid rgba(232,150,58,.22);color:#b89060;}"
        ".conf-banner.medium strong{color:#e8963a;}"
        ".conf-banner.low{background:rgba(224,92,92,.07);border:1px solid rgba(224,92,92,.22);color:#b06060;}"
        ".conf-banner.low strong{color:#e05c5c;}"
        ".thesis-meta{display:flex;align-items:center;justify-content:space-between;"
        "margin-bottom:12px;flex-wrap:wrap;gap:8px;}"
        ".read-time{font-size:11px;color:var(--muted);}"
        ".copy-btn{font-size:11px;color:var(--accent2);background:none;border:1px solid var(--border);"
        "border-radius:4px;padding:4px 10px;cursor:pointer;font-family:inherit;transition:all .15s;}"
        ".copy-btn:hover{background:var(--surface);}"
        ".copy-success{color:#4caf80!important;border-color:#4caf80!important;}"
        ".watch-list-wrap{display:flex;flex-direction:column;background:var(--surface);"
        "border:1px solid var(--border);border-radius:8px;overflow:hidden;}"
        ".watch-item{display:flex;align-items:flex-start;gap:16px;padding:14px 20px;"
        "border-bottom:1px solid var(--border);}"
        ".watch-item:last-child{border-bottom:none;}"
        ".watch-date{font-size:11px;font-weight:700;color:var(--accent2);white-space:nowrap;"
        "min-width:72px;padding-top:2px;font-family:'SF Mono','Consolas',monospace;}"
        ".watch-main{display:flex;flex-direction:column;gap:3px;}"
        ".watch-event{font-size:14px;font-weight:600;color:var(--text);}"
        ".watch-why{font-size:12px;color:var(--muted);}"
        ".share-row{display:flex;align-items:center;gap:8px;margin-top:28px;flex-wrap:wrap;}"
        ".share-label{font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);margin-right:4px;}"
        ".share-btn{display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:5px 14px;"
        "border-radius:4px;text-decoration:none;border:1px solid var(--border);color:var(--text);"
        "background:var(--surface);cursor:pointer;font-family:inherit;transition:border-color .15s;}"
        ".share-btn:hover{border-color:var(--muted);}"
        ".cross-section{margin-top:36px;padding-top:24px;border-top:1px solid var(--border);}"
        ".cross-label{font-size:10px;letter-spacing:.15em;text-transform:uppercase;"
        "color:var(--muted);margin-bottom:12px;}"
        ".cross-grid{display:flex;flex-wrap:wrap;gap:8px;}"
        ".cross-card{display:flex;align-items:center;gap:6px;padding:9px 14px;background:var(--surface);"
        "border:1px solid var(--border);border-radius:6px;text-decoration:none;color:var(--text);"
        "font-size:13px;transition:border-color .15s;}"
        ".cross-card:hover{border-color:var(--accent2);color:var(--accent2);}"
    )

    # ── JS 블록 ──────────────────────────────────────────────────
    _js_block = (
        "<script>"
        "function copyThesis(){"
        "var el=document.getElementById('thesis-text');"
        "var t=el?el.innerText:'';"
        "navigator.clipboard.writeText('「오늘의 테제」 '+t+' — '+location.href)"
        ".then(function(){"
        "var b=document.getElementById('copy-btn');"
        "b.textContent='✓ 복사됨';b.classList.add('copy-success');"
        "setTimeout(function(){b.textContent='\U0001f4cb 테제 복사';"
        "b.classList.remove('copy-success');},2000);"
        "}).catch(function(){});}"
        "window.addEventListener('DOMContentLoaded',function(){"
        "if(navigator.share){"
        "var nb=document.getElementById('share-native-btn');"
        "if(nb)nb.style.display='inline-flex';}});"
        "function shareNative(){"
        "navigator.share({title:document.title,url:location.href}).catch(function(){});}"
        "</script>"
    )

    # ── 투자 면책 조항 (경제 토픽 상단 표시) ───────────────────
    _disclaimer_html = ""
    if cfg.get("name", "").startswith("경제"):
        _disclaimer_html = (
            '<div class="disclaimer">'
            '<span class="disclaimer-icon">⚠</span>'
            '<span>본 분석은 공개 뉴스 정보를 바탕으로 한 <strong>참고 자료</strong>이며, '
            '<strong>투자 권유가 아닙니다.</strong> '
            '투자 결정에 따른 책임은 투자자 본인에게 있습니다.</span>'
            '</div>'
        )

    # ── 분석 기반 소스 섹션 ─────────────────────────────────────
    _source_html = ""
    if source_log:
        badges = "".join(
            f'<span class="src-badge">{_safe(name)} <em>{cnt}건</em></span>'
            for name, cnt in source_log
        )
        _source_html = (
            f'<div class="source-section">'
            f'<span class="source-label">분석 기반 소스</span>'
            f'<div class="source-badges">{badges}</div>'
            f'</div>'
        )
    metrics_rows = "".join(
        f"<tr><td>{_safe(m.get('label',''))}</td>"
        f"<td>{_safe(m.get('value',''))}</td>"
        f"<td>{_safe(m.get('meaning',''))}</td></tr>"
        for m in a.get("metrics", []) if isinstance(m, dict)
    )
    checklist_items = "".join(
        f'<div class="checklist-item"><div class="check-box"></div>'
        f'<div><div class="title">{_safe(c.get("title","") if isinstance(c, dict) else c)}</div>'
        f'<div class="desc">{_safe(c.get("desc","") if isinstance(c, dict) else "")}</div>'
        f'</div></div>'
        for c in a.get("checklist", [])
    )
    sa = a.get("scenario_a", {})
    sb = a.get("scenario_b", {})
    if isinstance(sa, str): sa = {"title": sa, "points": []}
    if isinstance(sb, str): sb = {"title": sb, "points": []}
    if not isinstance(sa, dict): sa = {}
    if not isinstance(sb, dict): sb = {}
    sa_points = "".join(f"<li>{_safe(p)}</li>" for p in sa.get("points", []))
    sb_points = "".join(f"<li>{_safe(p)}</li>" for p in sb.get("points", []))
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in cfg["tags"])

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="google-site-verification" content="LqVw-ScH1iEw7FKHSwyzzlYH2CZnQ_1TOmVCP8PHxMw"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{_seo_title}</title>
  <meta name="description" content="{_seo_desc}"/>
  <meta name="robots" content="index, follow"/>
  <link rel="canonical" href="{page_url}"/>
  <link rel="alternate" type="application/rss+xml" title="JAYCE 데일리 테제" href="https://jayce0321.github.io/daily-thesis/feed.xml"/>
  <meta property="og:type" content="article"/>
  <meta property="og:title" content="{_seo_title}"/>
  <meta property="og:description" content="{_seo_desc}"/>
  <meta property="og:url" content="{page_url}"/>
  <meta property="og:site_name" content="JAYCE 데일리 테제"/>
  <meta name="twitter:card" content="summary"/>
  <meta name="twitter:title" content="{_seo_title}"/>
  <meta name="twitter:description" content="{_seo_desc}"/>
  <meta name="keywords" content="{_seo_keywords}"/>
  <meta name="author" content="Jayce"/>
  {_json_ld_scripts}
  <style>
    :root{{--bg:#0d0f14;--surface:#161a23;--border:#252b3b;
      --accent:#e8b84b;--accent2:#5b8dee;--red:#e05c5c;
      --green:#4caf80;--text:#e2e6f0;--muted:#7a8299;--tag-bg:#1e2435;}}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--text);font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;line-height:1.75}}
    .hero{{position:relative;overflow:hidden;min-height:360px;display:flex;flex-direction:column;justify-content:flex-end;padding:56px 48px 48px;background:linear-gradient(160deg,#0d1a2e 0%,#0d0f14 60%)}}
    .hero::before{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 20% 80%,rgba(232,184,75,.08) 0%,transparent 50%),radial-gradient(circle at 80% 20%,rgba(91,141,238,.1) 0%,transparent 50%)}}
    .hero-eyebrow{{display:flex;align-items:center;gap:12px;margin-bottom:20px;position:relative}}
    .hero-date{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
    .hero-dot{{width:4px;height:4px;border-radius:50%;background:var(--accent)}}
    .hero-label{{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);font-weight:600}}
    .hero-tags{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px;position:relative}}
    .tag{{font-size:11px;padding:3px 10px;border-radius:20px;background:var(--tag-bg);border:1px solid var(--border);color:var(--muted)}}
    .hero h1{{font-size:clamp(22px,4vw,38px);font-weight:700;line-height:1.3;position:relative;max-width:800px}}
    .hero-sub{{margin-top:16px;font-size:15px;color:var(--muted);max-width:620px;position:relative}}
    .container{{max-width:860px;margin:0 auto;padding:56px 32px}}
    .thesis-block{{background:linear-gradient(135deg,#1a2235 0%,#161a23 100%);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:8px;padding:28px 32px;margin-bottom:48px}}
    .thesis-block .label{{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);font-weight:700;margin-bottom:12px}}
    .thesis-block p{{font-size:16px;line-height:1.8;color:#c8cfe0}}
    .section{{margin-bottom:52px}}
    .section-header{{display:flex;align-items:center;gap:12px;margin-bottom:24px;padding-bottom:14px;border-bottom:1px solid var(--border)}}
    .section-number{{width:28px;height:28px;border-radius:6px;background:var(--accent);color:#000;font-size:12px;font-weight:800;display:flex;align-items:center;justify-content:center}}
    .section-header h2{{font-size:17px;font-weight:700}}
    p{{margin-bottom:16px;color:#c0c8da;font-size:15px}}
    .data-table-wrap{{overflow-x:auto;margin:24px 0;border-radius:8px;border:1px solid var(--border)}}
    table{{width:100%;border-collapse:collapse}}
    thead tr{{background:#1a2235}}
    thead th{{padding:12px 16px;text-align:left;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap}}
    tbody tr{{border-top:1px solid var(--border)}}
    tbody tr:hover{{background:#1a2030}}
    tbody td{{padding:13px 16px;font-size:14px}}
    tbody td:first-child{{color:var(--muted);font-size:13px}}
    tbody td:nth-child(2){{font-weight:700;font-size:15px}}
    tbody td:nth-child(3){{color:#8a9ab8;font-size:13px}}
    .scenario-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:24px 0}}
    @media(max-width:600px){{.scenario-grid{{grid-template-columns:1fr}}.hero{{min-height:260px;padding:40px 20px 36px}}.container{{padding:36px 16px}}}}
    .scenario-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px 22px}}
    .scenario-card.green{{border-top:3px solid var(--green)}}.scenario-card.red{{border-top:3px solid var(--red)}}
    .scenario-label{{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}}
    .scenario-card.green .scenario-label{{color:var(--green)}}.scenario-card.red .scenario-label{{color:var(--red)}}
    .scenario-card h3{{font-size:14px;font-weight:700;margin-bottom:10px}}
    .scenario-card ul{{padding-left:16px}}
    .scenario-card li{{font-size:13px;color:#8a9ab8;margin-bottom:4px}}
    .checklist{{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}}
    .checklist-item{{display:flex;align-items:flex-start;gap:14px;padding:16px 20px;border-bottom:1px solid var(--border)}}
    .checklist-item:last-child{{border-bottom:none}}
    .check-box{{width:20px;height:20px;border-radius:4px;border:2px solid var(--border);flex-shrink:0;margin-top:1px}}
    .checklist-item .title{{font-size:14px;font-weight:600;margin-bottom:2px}}
    .checklist-item .desc{{font-size:12px;color:var(--muted)}}
    .callout{{background:#0f1825;border:1px solid #2a3a50;border-radius:8px;padding:24px 28px;margin-top:40px;position:relative;overflow:hidden}}
    .callout::before{{content:'"';position:absolute;top:-10px;left:20px;font-size:80px;color:rgba(232,184,75,.08);font-family:Georgia,serif;line-height:1}}
    .callout p{{font-size:15px;color:#b0bdd4;font-style:italic;position:relative}}
    footer{{border-top:1px solid var(--border);padding:24px 32px;text-align:center;font-size:12px;color:var(--muted)}}
    .hero-cover{{position:absolute;inset:0;z-index:0;overflow:hidden}}
    .hero-cover svg{{width:100%;height:100%;object-fit:cover}}
    .hero-eyebrow,.hero-tags,.hero h1,.hero-sub{{position:relative;z-index:1}}
    .chart-wrap{{margin:0 0 20px;border-radius:8px;overflow:hidden;border:1px solid var(--border)}}
    .chart-wrap svg{{width:100%;height:auto;display:block}}
    .back-link{{display:inline-block;margin:24px 32px 0;font-size:13px;color:var(--muted);text-decoration:none;}}
    .back-link:hover{{color:var(--accent)}}
    .faq-list{{display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin:0;padding:0;list-style:none;}}
    .faq-item{{padding:18px 22px;border-bottom:1px solid var(--border);}}
    .faq-item:last-child{{border-bottom:none;}}
    .faq-q{{font-size:14px;font-weight:700;color:var(--accent);margin-bottom:8px;display:block;}}
    .faq-a{{font-size:13px;color:#8a9ab8;line-height:1.75;margin:0;display:block;}}
    .section-number.q-badge{{background:var(--accent2);font-size:11px;font-weight:800;}}
    .disclaimer{{display:flex;align-items:flex-start;gap:10px;background:rgba(232,150,58,.07);border:1px solid rgba(232,150,58,.22);border-radius:6px;padding:12px 18px;margin-bottom:28px;font-size:13px;color:#b89060;line-height:1.6;}}
    .disclaimer strong{{color:#e8963a;}}
    .disclaimer-icon{{flex-shrink:0;font-size:15px;margin-top:1px;}}
    .source-section{{display:flex;align-items:center;flex-wrap:wrap;gap:10px;padding:16px 0;border-top:1px solid var(--border);margin-top:40px;}}
    .source-label{{font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap;}}
    .source-badges{{display:flex;flex-wrap:wrap;gap:6px;}}
    .src-badge{{font-size:12px;padding:3px 10px;background:var(--surface);border:1px solid var(--border);border-radius:20px;color:var(--muted);}}
    .src-badge em{{font-style:normal;color:var(--accent2);font-weight:600;margin-left:4px;}}
    {_extra_css}
  </style>
  {_js_block}
</head>
<body>
<a class="back-link" href="{cfg['index_file']}">← {cfg['name']} 목록</a>
<section class="hero">
  {('<div class="hero-cover">' + cover_svg + '</div>') if cover_svg else ''}
  <div class="hero-eyebrow">
    <span class="hero-date">{TODAY_KR}</span>
    <span class="hero-dot"></span>
    <span class="hero-label">{cfg['icon']} {cfg['name']} Daily Thesis</span>
  </div>
  <div class="hero-tags">{tags_html}</div>
  <h1>{a['thesis_title']}</h1>
  <p class="hero-sub">{a['one_line']}</p>
</section>
<div class="container">
  {_confidence_banner}
  {_disclaimer_html}
  <div class="thesis-meta">
    <span class="read-time">약 {_read_min}분 읽기</span>
    <button class="copy-btn" id="copy-btn" onclick="copyThesis()">📋 테제 복사</button>
  </div>
  <div class="thesis-block" id="direct-answer">
    <div class="label">오늘의 핵심 테제</div>
    <p id="thesis-text">{a['one_line']}</p>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-number">1</div><h2>왜 이게 중요한가</h2></div>
    <p>{a['why_important']}</p>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-number">2</div><h2>숫자로 보는 근거</h2></div>
    {('<div class="chart-wrap">' + chart_svg + '</div>') if chart_svg else ''}
    <div class="data-table-wrap">
      <table>
        <thead><tr><th>지표</th><th>수치</th><th>의미</th></tr></thead>
        <tbody>{metrics_rows}</tbody>
      </table>
    </div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-number">3</div><h2>시나리오 분기</h2></div>
    <div class="scenario-grid">
      <div class="scenario-card green">
        <div class="scenario-label">시나리오 A</div>
        <h3>{sa.get('title','')}</h3><ul>{sa_points}</ul>
      </div>
      <div class="scenario-card red">
        <div class="scenario-label">시나리오 B</div>
        <h3>{sb.get('title','')}</h3><ul>{sb_points}</ul>
      </div>
    </div>
  </div>
  <div class="section">
    <div class="section-header"><div class="section-number">4</div><h2>체크리스트</h2></div>
    <div class="checklist">{checklist_items}</div>
  </div>
  {_watch_html}
  {_faq_html}
  <div class="callout"><p>{a.get('closing', a.get('one_line', ''))}</p></div>
  {_share_html}
  {_source_html}
  {_cross_html}
</div>
<footer>{cfg['footer']}</footer>
</body>
</html>"""

# ── index 페이지 보장 ─────────────────────────────────────────
INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="google-site-verification" content="LqVw-ScH1iEw7FKHSwyzzlYH2CZnQ_1TOmVCP8PHxMw"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{index_title}}</title>
  <script type="application/ld+json">
  {"@context":"https://schema.org","@type":"WebSite","name":"JAYCE 데일리 테제","url":"https://jayce0321.github.io/daily-thesis","description":"경제·투자·정치·컬처 — 시장을 관통하는 하나의 테제 by Jayce","inLanguage":"ko","publisher":{"@type":"Person","name":"Jayce"}}
  </script>
  <style>
    :root{{--bg:#0d0f14;--surface:#161a23;--border:#252b3b;--accent:#e8b84b;--text:#e2e6f0;--muted:#7a8299;}}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--text);font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;min-height:100vh;}}
    header{{padding:48px 40px 32px;border-bottom:1px solid var(--border);}}
    header h1{{font-size:22px;font-weight:700;}}
    header p{{font-size:13px;color:var(--muted);margin-top:6px;}}
    .nav{{display:flex;gap:16px;padding:16px 40px;border-bottom:1px solid var(--border);font-size:13px;}}
    .nav a{{color:var(--muted);text-decoration:none;}} .nav a:hover{{color:var(--accent)}}
    .container{{max-width:760px;margin:0 auto;padding:40px 32px;}}
    .post-list{{display:flex;flex-direction:column;gap:1px;}}
    .post-item{{display:flex;align-items:center;justify-content:space-between;padding:20px 0;border-bottom:1px solid var(--border);text-decoration:none;color:var(--text);transition:color .15s;}}
    .post-item:hover{{color:var(--accent);}}
    .post-title{{font-size:15px;font-weight:600;}}
    .post-sub{{font-size:12px;color:var(--muted);margin-top:4px;}}
    .post-date{{font-size:12px;color:var(--muted);white-space:nowrap;margin-left:24px;}}
    footer{{text-align:center;padding:32px;font-size:12px;color:var(--muted);border-top:1px solid var(--border);}}
  </style>
</head>
<body>
  <header>
    <h1>{{icon}} {{topic_name}} 데일리 테제</h1>
    <p>{{subtitle}}</p>
  </header>
  <nav class="nav">
    <a href="index.html">📊 경제·투자</a>
    <a href="politics.html">🏛️ 정치</a>
    <a href="culture.html">🎬 컬처</a>
  </nav>
  <div class="container">
    <div class="post-list">
    </div>
  </div>
  <footer>데일리 테제 · {{topic_name}} · by Jayce</footer>
</body>
</html>"""

def ensure_index(cfg):
    index_path = os.path.join(REPO_DIR, cfg["index_file"])
    if not os.path.exists(index_path):
        content = (INDEX_TEMPLATE
            .replace("{{index_title}}", cfg["index_title"])
            .replace("{{icon}}", cfg["icon"])
            .replace("{{topic_name}}", cfg["name"])
            .replace("{{subtitle}}", cfg["index_subtitle"]))
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)
        log(f"인덱스 페이지 생성: {cfg['index_file']}")

# ── 4. 게시 + 알림 ───────────────────────────────────────────
def _ping_indexnow(page_url):
    """IndexNow API 핑 — 발행 즉시 Bing·Naver에 URL 알림 (키 없으면 스킵)"""
    if not _INDEXNOW_KEY:
        return
    host = "jayce0321.github.io"
    body = json.dumps({
        "host": host,
        "key": _INDEXNOW_KEY,
        "keyLocation": f"https://{host}/{_INDEXNOW_KEY}.txt",
        "urlList": [page_url],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": _BOT_UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            log(f"IndexNow 핑 완료 (HTTP {r.status})")
    except Exception as e:
        log(f"IndexNow 핑 실패 (무시): {e}")


def publish(html_content, analysis, cfg):
    ensure_index(cfg)

    html_path = os.path.join(REPO_DIR, cfg["html_name"])
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    log(f"HTML 저장: {html_path}")

    index_path = os.path.join(REPO_DIR, cfg["index_file"])
    with open(index_path, "r", encoding="utf-8") as f:
        index = f.read()

    def _make_entry():
        t = _safe(analysis.get('thesis_title', ''))
        s = _safe(analysis.get('one_line', '')[:40])
        return (
            f'      <a class="post-item" href="{cfg["html_name"]}">\n'
            f'        <div>\n'
            f'          <div class="post-title">{t}</div>\n'
            f'          <div class="post-sub">{s}...</div>\n'
            f'        </div>\n'
            f'        <div class="post-date">{TODAY_KR}</div>\n'
            f'      </a>'
        )

    if f'href="{cfg["html_name"]}"' not in index:
        index = index.replace(
            '<div class="post-list">',
            '<div class="post-list">\n' + _make_entry()
        )
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index)
        log(f"인덱스 업데이트: {cfg['index_file']}")

    # page_url은 피드/sitemap에도 사용하므로 git 처리 전에 확정
    page_url = f"{_PAGES_URL}/{cfg['html_name']}"

    # RSS 피드 + sitemap 업데이트 (git add 전에 파일 생성)
    _update_feed(analysis, cfg, page_url)
    _update_sitemap()

    _extra_files = ["feed.xml", "sitemap.xml"]

    _did_push = False  # 실제로 새 커밋이 push됐는지 추적 (Naver 중복 방지)

    if not IS_CI:
        os.chdir(REPO_DIR)
        subprocess.run(["git", "fetch", "origin"], check=True)
        subprocess.run(["git", "reset", "--hard", "origin/main"], check=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        ensure_index(cfg)
        with open(index_path, "r", encoding="utf-8") as f:
            idx = f.read()
        if f'href="{cfg["html_name"]}"' not in idx:
            idx = idx.replace('<div class="post-list">', '<div class="post-list">\n' + _make_entry())
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(idx)
        _update_feed(analysis, cfg, page_url)
        _update_sitemap()
        subprocess.run(["git", "add", cfg["html_name"], cfg["index_file"]] + _extra_files, check=True)
        staged = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if staged.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"{cfg['name']} 데일리 테제 {TODAY_KR}"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            _did_push = True
    else:
        # CI 환경: 이전 토픽 push 반영 후 현재 파일 직접 커밋
        # → daily.yml의 git pull --rebase 도달 시 이미 committed 상태라 충돌 없음
        os.chdir(REPO_DIR)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"],
                       capture_output=True, check=False)
        subprocess.run(["git", "add", cfg["html_name"], cfg["index_file"]] + _extra_files, check=False)
        staged = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if staged.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"{cfg['name']} 데일리 테제 {TODAY_KR} [자동]"],
                           capture_output=True, check=False)
            subprocess.run(["git", "push", "origin", "main"], check=False)
            _did_push = True

    log("GitHub Pages 게시 완료")
    log(f"→ {page_url}")

    # IndexNow 핑 (새 발행 시만)
    if _did_push:
        _ping_indexnow(page_url)

    # Telegram 알림
    channel_id = (
        os.environ.get(cfg["channel_env"])
        or cfg.get("channel_id", "")
        or os.environ.get("TELEGRAM_CHAT_ID", "")
    )
    if not (BOT_TOKEN and channel_id):
        log("텔레그램 채널 미설정 — 알림 생략")
        return

    text = (
        f"{cfg['icon']} <b>데일리 테제 | {cfg['name']}</b>  {TODAY_KR}\n\n"
        f"<b>{analysis['thesis_title']}</b>\n\n"
        f"{analysis['one_line']}\n\n"
        "━━━━━━━━━━━━\n"
        "✅ 체크리스트\n"
        + "\n".join(
            f"• {c['title'] if isinstance(c, dict) else c}"
            for c in analysis.get("checklist", [])
        )
        + f"\n\n🔗 {page_url}\n\n"
        f"{cfg['tg_hashtag']}"
    )

    data = json.dumps({
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
        if result.get("ok"):
            log("텔레그램 알림 전송 완료")
        else:
            log(f"텔레그램 오류: {result}")
    except Exception as e:
        log(f"텔레그램 알림 실패 (무시): {e}")

    # 네이버 블로그 (신규 발행 시만 — _did_push=False면 중복이므로 스킵)
    if _did_push:
        _post_to_tistory(analysis, cfg, page_url)

# ── 메인 ─────────────────────────────────────────────────────
def main():
    log(f"=== 데일리 테제 시작 ({TODAY_KR}) topic={TOPIC} ===")

    if TOPIC not in TOPIC_CONFIG:
        print(f"❌ 알 수 없는 TOPIC: {TOPIC}. 사용 가능: {', '.join(TOPIC_CONFIG)}")
        sys.exit(1)

    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY 환경변수가 없습니다.")
        sys.exit(1)

    cfg              = TOPIC_CONFIG[TOPIC]
    news, source_log = fetch_news(cfg)
    if not news:
        log("⚠️ 뉴스 수집 실패 — 기본 프롬프트로 진행")
        news       = [f"{cfg['name']} 오늘의 주요 동향 분석 필요"]
        source_log = []
    elif len(news) < 5:
        log(f"⚠️ 품질 게이트: 뉴스 {len(news)}건 (기준 5건) — Claude가 low 확신도를 반환할 수 있음")

    # 실시간 경제 수치 수집 (경제 토픽만, FRED/ECOS 키 있을 때만)
    live_data = []
    if cfg.get("name", "").startswith("경제"):
        live_data = fetch_live_data()

    analysis = call_claude(news, cfg, live_data=live_data)
    cover_svg, chart_svg = generate_svgs(analysis)
    _page_url = f"{_PAGES_URL}/{cfg['html_name']}"
    html = build_html(analysis, cfg, cover_svg, chart_svg,
                      page_url=_page_url, source_log=source_log)
    publish(html, analysis, cfg)

    log(f"=== {cfg['name']} 완료 ===")

if __name__ == "__main__":
    main()
