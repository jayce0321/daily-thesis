#!/usr/bin/env python3
"""
JAYCE 리서치 모듈
- 뉴스 검색 (Google News RSS)
- 주가 조회 (Yahoo Finance)
- URL 본문 추출
- 웹 키워드 검색
"""

import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


# ── 뉴스 검색 ─────────────────────────────────────────────────
def search_news(query: str, max_items: int = 8) -> list[dict]:
    """Google News RSS로 뉴스 검색. 제목/링크/발행일 반환."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            xml = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return [{"error": str(e)}]

    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    results = []
    for item in items[:max_items]:
        title = re.search(r"<title>(.*?)</title>", item)
        link  = re.search(r"<link>(.*?)</link>|<link/>(.*?)<", item)
        pub   = re.search(r"<pubDate>(.*?)</pubDate>", item)
        src   = re.search(r"<source[^>]*>(.*?)</source>", item)

        title = _strip_cdata(title.group(1)) if title else ""
        link  = (link.group(1) or link.group(2) or "").strip() if link else ""
        pub   = pub.group(1).strip() if pub else ""
        src   = _strip_cdata(src.group(1)) if src else ""

        if title:
            results.append({"title": title, "link": link, "pub": pub, "source": src})
    return results


def search_news_en(query: str, max_items: int = 5) -> list[dict]:
    """영문 Google News RSS 검색 (글로벌 뉴스용)."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            xml = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return [{"error": str(e)}]

    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    results = []
    for item in items[:max_items]:
        title = re.search(r"<title>(.*?)</title>", item)
        pub   = re.search(r"<pubDate>(.*?)</pubDate>", item)
        src   = re.search(r"<source[^>]*>(.*?)</source>", item)
        title = _strip_cdata(title.group(1)) if title else ""
        pub   = pub.group(1).strip() if pub else ""
        src   = _strip_cdata(src.group(1)) if src else ""
        if title:
            results.append({"title": title, "pub": pub, "source": src})
    return results


def _strip_cdata(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    return re.sub(r"<[^>]+>", "", text).strip()


def format_news(items: list[dict], title: str = "뉴스") -> str:
    if not items or "error" in items[0]:
        return f"❌ {title} 검색 실패"
    lines = [f"📰 *{title}*\n"]
    for i, it in enumerate(items, 1):
        pub = it.get("pub", "")
        if pub:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub).astimezone(KST)
                pub = dt.strftime("%m/%d %H:%M")
            except Exception:
                pub = pub[:16]
        src = f" — {it['source']}" if it.get("source") else ""
        lines.append(f"{i}. {it['title']}{src} `{pub}`")
    return "\n".join(lines)


# ── 주가 조회 ─────────────────────────────────────────────────
# 한국 주요 종목 코드 매핑
KR_STOCK_MAP = {
    "삼성전자": "005930.KS", "삼성": "005930.KS",
    "sk하이닉스": "000660.KS", "하이닉스": "000660.KS",
    "lg에너지솔루션": "373220.KS", "엘지에너지": "373220.KS",
    "현대차": "005380.KS", "현대자동차": "005380.KS",
    "카카오": "035720.KS", "네이버": "035420.KS",
    "셀트리온": "068270.KS", "기아": "000270.KS",
    "포스코": "005490.KS", "kb금융": "105560.KS",
    "신한지주": "055550.KS", "하나금융": "086790.KS",
}

CRYPTO_MAP = {
    "비트코인": "BTC-USD", "btc": "BTC-USD",
    "이더리움": "ETH-USD", "eth": "ETH-USD",
    "솔라나": "SOL-USD", "sol": "SOL-USD",
    "리플": "XRP-USD", "xrp": "XRP-USD",
}


def get_stock(ticker: str) -> dict:
    """Yahoo Finance에서 주가 정보 조회."""
    # 한국어 종목명 → 티커 변환
    lower = ticker.lower().strip()
    ticker = KR_STOCK_MAP.get(lower, CRYPTO_MAP.get(lower, ticker.upper()))

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
        f"?interval=1d&range=5d"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        meta   = result["meta"]

        price    = meta.get("regularMarketPrice", 0)
        prev     = meta.get("chartPreviousClose", meta.get("previousClose", 0))
        currency = meta.get("currency", "")
        name     = meta.get("longName") or meta.get("shortName") or ticker
        mkt_cap  = meta.get("marketCap")
        volume   = meta.get("regularMarketVolume")

        change     = price - prev if prev else 0
        change_pct = (change / prev * 100) if prev else 0
        arrow      = "▲" if change >= 0 else "▼"
        sign       = "+" if change >= 0 else ""

        return {
            "ok": True,
            "ticker": ticker,
            "name": name,
            "price": price,
            "currency": currency,
            "change": change,
            "change_pct": change_pct,
            "arrow": arrow,
            "sign": sign,
            "mkt_cap": mkt_cap,
            "volume": volume,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "ticker": ticker}


def format_stock(d: dict) -> str:
    if not d["ok"]:
        return f"❌ `{d['ticker']}` 조회 실패: {d['error']}"

    ccy = d["currency"]
    price_str = f"{d['price']:,.2f}" if d['price'] < 10000 else f"{d['price']:,.0f}"
    change_str = f"{d['sign']}{d['change']:,.2f} ({d['sign']}{d['change_pct']:.2f}%)"

    lines = [
        f"📊 *{d['name']}* (`{d['ticker']}`)",
        f"현재가: *{price_str} {ccy}* {d['arrow']} {change_str}",
    ]
    if d.get("mkt_cap"):
        cap = d["mkt_cap"]
        if cap >= 1e12:
            lines.append(f"시총: {cap/1e12:.2f}조 {ccy}")
        elif cap >= 1e8:
            lines.append(f"시총: {cap/1e8:.0f}억 {ccy}")
    if d.get("volume"):
        lines.append(f"거래량: {d['volume']:,}")

    return "\n".join(lines)


# ── URL 본문 추출 ─────────────────────────────────────────────
def fetch_url(url: str, max_chars: int = 4000) -> dict:
    """URL에서 제목 + 본문 텍스트 추출."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
        html = raw.decode(enc, errors="replace")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # 제목 추출
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else url

    # 본문 추출
    html = re.sub(r"<(style|script|nav|header|footer|aside|noscript|iframe|form)[^>]*>.*?</\1>",
                  "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    return {"ok": True, "title": title, "text": text[:max_chars], "url": url}


# ── 간단 웹 검색 (DuckDuckGo 텍스트) ─────────────────────────
def quick_search(query: str) -> str:
    """DuckDuckGo instant answer API로 빠른 사실 조회."""
    encoded = urllib.parse.quote(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        abstract = data.get("AbstractText", "").strip()
        answer   = data.get("Answer", "").strip()
        return answer or abstract or ""
    except Exception:
        return ""
