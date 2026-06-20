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
    # 1순위: 환경변수 (daily.yml inputs 방식)
    env_t = os.environ.get("TOPIC", "").lower().strip()
    if env_t in ("economy", "politics", "culture"):
        return env_t
    # 2순위: 파일 큐 (_pending_topic.txt) — Railway→GitHub API로 미리 생성
    queue_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_pending_topic.txt")
    if os.path.exists(queue_file):
        try:
            with open(queue_file) as _f:
                queued = _f.read().strip().lower()
            os.remove(queue_file)
            if queued in ("economy", "politics", "culture"):
                return queued
        except Exception:
            pass
    return "economy"

TOPIC             = _resolve_topic()
REPO_DIR          = os.path.dirname(os.path.abspath(__file__))
IS_CI             = os.environ.get("GITHUB_ACTIONS") == "true"

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

_CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_body(url, max_chars=900):
    """기사 URL 본문 추출. 실패 시 빈 문자열."""
    if not url or "news.google.com" in url:
        return ""
    try:
        from bs4 import BeautifulSoup
        import re as _re
        req = urllib.request.Request(url, headers=_CRAWL_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
        html = raw.decode(enc, errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "figure", "noscript", "iframe", "form"]):
            tag.decompose()
        body = soup.find("article") or soup.find("main") or soup.body
        if not body:
            return ""
        text = _re.sub(r"\s+", " ", body.get_text(separator=" ")).strip()
        return text[:max_chars]
    except Exception:
        return ""


def _parse_direct_rss(rss_url, limit):
    """직접 URL RSS 파싱 → [{title, url, body}] 반환."""
    import re as _re
    results = []
    try:
        req = urllib.request.Request(
            rss_url, headers={"User-Agent": "Mozilla/5.0"})
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
            results.append({"title": title, "url": url, "body": ""})
            if len(results) >= limit:
                break
    except Exception as e:
        log(f"  직접 RSS 오류: {e}")
    return results


# ── 1. 뉴스 수집 ─────────────────────────────────────────────
def fetch_news(cfg):
    log("뉴스 수집 중...")
    import re as _re

    seen = set()
    articles = []   # {title, url, body, desc}

    # ① 신뢰 RSS (직접 URL → 본문 크롤링)
    topic_key = TOPIC  # "economy" | "politics" | "culture"
    for source_name, rss_url, limit in _DIRECT_RSS.get(topic_key, []):
        items = _parse_direct_rss(rss_url, limit)
        added = 0
        for art in items:
            if art["title"] in seen or len(art["title"]) < 6:
                continue
            seen.add(art["title"])
            articles.append(art)
            added += 1
        log(f"  [{source_name}] {added}건")

    # 본문 크롤링
    log(f"  → 본문 크롤링 ({len(articles)}건)...")
    ok = 0
    for art in articles:
        art["body"] = _fetch_body(art["url"])
        if art["body"]:
            ok += 1
    log(f"  → 본문 확보: {ok}/{len(articles)}건")

    # ② Google News RSS (토픽별 쿼리 → 제목+desc 보완)
    topic_queries = cfg.get("queries", [])
    common_queries = [
        ("글로벌 금융시장 매크로 경제 오늘", "ko"),
        ("Federal Reserve interest rate economy today", "en"),
    ]
    all_queries = [(q, "ko") for q in topic_queries] + common_queries

    for q, lang in all_queries:
        try:
            encoded = urllib.parse.quote(q)
            if lang == "en":
                rss_url = (f"https://news.google.com/rss/search"
                           f"?q={encoded}&hl=en&gl=US&ceid=US:en")
            else:
                rss_url = (f"https://news.google.com/rss/search"
                           f"?q={encoded}&hl=ko&gl=KR&ceid=KR:ko")
            req = urllib.request.Request(
                rss_url, headers={"User-Agent": "Mozilla/5.0"})
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
                    title = _re.sub(
                        r'\s*-\s*[^-]{2,30}$', '', title).strip()
                    if title in seen or len(title) < 8:
                        continue
                    seen.add(title)
                    desc = ""
                    if d_m:
                        desc = _re.sub(
                            r'<[^>]+>', '', d_m.group(1)).strip()[:120]
                    articles.append({"title": title, "url": "", "body": "", "desc": desc})
        except Exception as e:
            log(f"  [{q[:18]}] 수집 오류: {e}")

    log(f"뉴스 총 {len(articles)}건 수집 완료")
    return articles[:28]


def call_claude(news_headlines, cfg):
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
    # 본문 확보 기사가 있으면 숫자 신뢰도 강조
    body_count = sum(1 for a in news_headlines
                     if isinstance(a, dict) and a.get("body"))
    if body_count > 0:
        instruction += (
            f"\n\n※ {body_count}개 기사는 본문이 포함되어 있습니다. "
            "metrics의 수치는 반드시 본문에서 확인된 것만 사용하고, "
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
                "closing": {"type": "string", "description": "마무리 한 줄"}
            },
            "required": ["thesis_title", "one_line", "why_important", "metrics",
                         "scenario_a", "scenario_b", "checklist", "closing"]
        }
    }

    data = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 2800,
        "tools": [tool_def],
        "tool_choice": {"type": "tool", "name": "save_thesis"},
        "messages": [{
            "role": "user",
            "content": f"{instruction}\n\n수집된 뉴스:\n{headlines_text}"
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

def build_html(a, cfg, cover_svg="", chart_svg=""):
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>데일리 테제 | {cfg['name']} | {TODAY_KR}</title>
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
  </style>
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
  <div class="thesis-block">
    <div class="label">오늘의 핵심 테제</div>
    <p>{a['one_line']}</p>
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
  <div class="callout"><p>{a.get('closing', a.get('one_line', ''))}</p></div>
</div>
<footer>{cfg['footer']}</footer>
</body>
</html>"""

# ── index 페이지 보장 ─────────────────────────────────────────
INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{index_title}}</title>
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
        subprocess.run(["git", "add", cfg["html_name"], cfg["index_file"]], check=True)
        staged = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if staged.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"{cfg['name']} 데일리 테제 {TODAY_KR}"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
    else:
        # CI 환경: 이전 토픽 push 반영 후 현재 파일 직접 커밋
        # → daily.yml의 git pull --rebase 도달 시 이미 committed 상태라 충돌 없음
        os.chdir(REPO_DIR)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"],
                       capture_output=True, check=False)
        subprocess.run(["git", "add", cfg["html_name"], cfg["index_file"]], check=False)
        staged = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if staged.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"{cfg['name']} 데일리 테제 {TODAY_KR} [자동]"],
                           capture_output=True, check=False)
            subprocess.run(["git", "push", "origin", "main"], check=False)

    log("GitHub Pages 게시 완료")
    page_url = f"https://jayce0321.github.io/daily-thesis/{cfg['html_name']}"
    log(f"→ {page_url}")

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

# ── 메인 ─────────────────────────────────────────────────────
def main():
    log(f"=== 데일리 테제 시작 ({TODAY_KR}) topic={TOPIC} ===")

    if TOPIC not in TOPIC_CONFIG:
        print(f"❌ 알 수 없는 TOPIC: {TOPIC}. 사용 가능: {', '.join(TOPIC_CONFIG)}")
        sys.exit(1)

    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY 환경변수가 없습니다.")
        sys.exit(1)

    cfg  = TOPIC_CONFIG[TOPIC]
    news = fetch_news(cfg)
    if not news:
        log("⚠️ 뉴스 수집 실패 — 기본 프롬프트로 진행")
        news = [f"{cfg['name']} 오늘의 주요 동향 분석 필요"]

    analysis = call_claude(news, cfg)
    cover_svg, chart_svg = generate_svgs(analysis)
    html = build_html(analysis, cfg, cover_svg, chart_svg)
    publish(html, analysis, cfg)

    log(f"=== {cfg['name']} 완료 ===")

if __name__ == "__main__":
    main()
