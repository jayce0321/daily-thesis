#!/usr/bin/env python3
"""
JAYCE 데일리 테제 + 리서치 챗봇
- 테제 요약 및 Q&A
- 뉴스 검색 (/news)
- 주가 조회 (/stock)
- URL 분석 (/url)
- 심층 리서치 (/research)
- 자유 질문 자동 라우팅
"""

import os
import sys
import json
import time
import re
import glob
from datetime import datetime, timezone, timedelta
from pathlib import Path

import urllib.request

# ── 환경 변수 ─────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent.resolve()
ENV_FILE = REPO_DIR / ".env"


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()

BOT_TOKEN         = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ALLOWED_CHAT_ID   = int(os.environ.get("TELEGRAM_CHAT_ID", "5066621346"))
KST               = timezone(timedelta(hours=9))

if not BOT_TOKEN or not ANTHROPIC_API_KEY:
    print("❌ .env에 TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY 필요")
    sys.exit(1)

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 대화 히스토리 (문맥 유지, 최대 10턴)
_history: list[dict] = []
MAX_HISTORY = 10


# ── 텔레그램 헬퍼 ─────────────────────────────────────────────
def tg(method, http_timeout=15, **params):
    data = json.dumps(params).encode()
    req  = urllib.request.Request(
        f"{TG_API}/{method}", data=data,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=http_timeout) as r:
        return json.loads(r.read())


def send(chat_id, text, parse_mode="Markdown"):
    # Telegram 메시지 4096자 제한 분할
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            tg("sendMessage", chat_id=chat_id, text=chunk,
               parse_mode=parse_mode, disable_web_page_preview=True)
        except Exception:
            try:
                tg("sendMessage", chat_id=chat_id, text=chunk)
            except Exception as e:
                print(f"[send error] {e}")


def send_typing(chat_id):
    try:
        tg("sendChatAction", chat_id=chat_id, action="typing")
    except Exception:
        pass


def now_str():
    return datetime.now(KST).strftime("%H:%M:%S")


# ── 테제 콘텐츠 로드 ──────────────────────────────────────────
TOPIC_MAP = {
    "economy":  ("경제·투자", ""),
    "politics": ("정치",     "-politics"),
    "culture":  ("컬처",     "-culture"),
}


def load_thesis(topic="economy", date_str=None):
    suffix = TOPIC_MAP[topic][1]
    if date_str:
        path = REPO_DIR / f"{date_str}{suffix}.html"
    else:
        files = sorted(glob.glob(str(REPO_DIR / f"*{suffix}.html")))
        files = [f for f in files if re.search(r"\d{4}-\d{2}-\d{2}", f)]
        if not files:
            return None, None
        path = Path(files[-1])

    if not path.exists():
        return None, None

    html  = path.read_text(encoding="utf-8")
    date  = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    date  = date.group(1) if date else "최근"

    html  = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    html  = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text  = re.sub(r"<[^>]+>", " ", html)
    text  = re.sub(r"\s+", " ", text).strip()
    return text[:6000], date


def get_all_today():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    parts = []
    for topic, (name, _) in TOPIC_MAP.items():
        text, date = load_thesis(topic, today)
        if text:
            parts.append(f"[{name}]\n{text[:1500]}")
    return "\n\n".join(parts) if parts else None


# ── Claude API ────────────────────────────────────────────────
def ask_claude(user_msg: str, context: str = "", system_extra: str = "",
               model: str = "claude-haiku-4-5-20251001",
               use_history: bool = False) -> str:

    base_system = (
        "당신은 JAYCE 데일리 테제 봇입니다. "
        "Jaeho Lee의 경제·금융·리서치 AI 어시스턴트입니다.\n"
        "답변 규칙:\n"
        "- 핵심만 짧고 명확하게 (마크다운 사용 가능)\n"
        "- 숫자/날짜는 정확하게\n"
        "- 투자 권유는 하지 않되 시장 해석은 제시\n"
        "- 한국어로 답변"
    )
    if context:
        base_system += f"\n\n참고 데이터:\n---\n{context}\n---"
    if system_extra:
        base_system += f"\n\n{system_extra}"

    messages = []
    if use_history and _history:
        messages = _history[-MAX_HISTORY:]
    messages.append({"role": "user", "content": user_msg})

    data = json.dumps({
        "model": model,
        "max_tokens": 1500,
        "system": base_system,
        "messages": messages,
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=data,
        headers={
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        result = json.loads(r.read())
    answer = result["content"][0]["text"]

    if use_history:
        _history.append({"role": "user", "content": user_msg})
        _history.append({"role": "assistant", "content": answer})
        if len(_history) > MAX_HISTORY * 2:
            del _history[:2]

    return answer


# ── 리서치 기능 ───────────────────────────────────────────────
def cmd_news(chat_id, query):
    """뉴스 검색 + Claude 요약."""
    if not query:
        send(chat_id, "사용법: `/news 검색어`\n예: `/news 연준 금리`")
        return

    send_typing(chat_id)
    from research import search_news, search_news_en, format_news

    ko_news = search_news(query, max_items=6)
    en_news = search_news_en(query + " news", max_items=4)

    context_lines = []
    for n in ko_news:
        if "error" not in n:
            context_lines.append(f"- {n['title']} ({n.get('source','')})")
    for n in en_news:
        if "error" not in n:
            context_lines.append(f"- {n['title']} ({n.get('source','')})")

    context = "\n".join(context_lines)

    send_typing(chat_id)
    summary = ask_claude(
        f"'{query}' 관련 최신 뉴스 헤드라인들을 분석해서 핵심 트렌드와 시사점을 3~5줄로 요약해줘.",
        context=context,
        system_extra="뉴스 요약 전문가처럼 핵심 흐름을 파악해서 인사이트 중심으로 답변."
    )

    news_list = format_news(ko_news[:5], f"'{query}' 뉴스")
    send(chat_id, f"{news_list}\n\n💡 *AI 요약*\n{summary}")
    print(f"[{now_str()}] /news: {query}")


def cmd_stock(chat_id, ticker):
    """주가 조회 + 간단 분석."""
    if not ticker:
        send(chat_id, "사용법: `/stock 티커 또는 종목명`\n예: `/stock AAPL` `/stock 삼성전자` `/stock 비트코인`")
        return

    send_typing(chat_id)
    from research import get_stock, format_stock, search_news

    stock = get_stock(ticker)
    stock_text = format_stock(stock)

    if stock["ok"]:
        news = search_news(f"{stock['name']} {ticker} 주가", max_items=3)
        news_ctx = "\n".join(
            f"- {n['title']}" for n in news if "error" not in n
        )
        send_typing(chat_id)
        analysis = ask_claude(
            f"{stock['name']}({ticker}) 현재 주가 {stock['price']} {stock['currency']}, "
            f"전일 대비 {stock['sign']}{stock['change_pct']:.2f}% 에 대해 간략히 분석해줘.",
            context=news_ctx,
            system_extra="주가 분석 시 최근 뉴스 맥락을 반영해서 2~3문장으로 요약."
        )
        send(chat_id, f"{stock_text}\n\n💡 {analysis}")
    else:
        send(chat_id, stock_text)

    print(f"[{now_str()}] /stock: {ticker}")


def cmd_url(chat_id, url):
    """URL 내용 요약."""
    if not url or not url.startswith("http"):
        send(chat_id, "사용법: `/url https://...`\n예: `/url https://reuters.com/article/...`")
        return

    send_typing(chat_id)
    from research import fetch_url

    result = fetch_url(url)
    if not result["ok"]:
        send(chat_id, f"❌ URL 접근 실패: {result['error']}")
        return

    send_typing(chat_id)
    summary = ask_claude(
        "이 문서의 핵심 내용을 요약하고 주요 인사이트를 3~5개 bullet point로 정리해줘.",
        context=f"제목: {result['title']}\n\n내용:\n{result['text']}",
        system_extra="문서 분석가처럼 핵심을 정확히 뽑아내되, 원문에 없는 내용은 추가하지 마."
    )

    send(chat_id, f"🔗 *{result['title']}*\n\n{summary}\n\n`{url}`")
    print(f"[{now_str()}] /url: {url[:60]}")


def cmd_research(chat_id, topic):
    """심층 리서치: 뉴스 + 테제 + Claude Sonnet 분석."""
    if not topic:
        send(chat_id, "사용법: `/research 주제`\n예: `/research 미국 금리인하 전망`")
        return

    send(chat_id, f"🔍 *'{topic}'* 리서치 시작...\n_(뉴스 수집 → 분석 → 요약 순으로 진행합니다)_")
    send_typing(chat_id)

    from research import search_news, search_news_en

    ko_news = search_news(topic, max_items=8)
    en_news = search_news_en(topic, max_items=5)

    ko_lines = [f"- {n['title']} ({n.get('source','')})" for n in ko_news if "error" not in n]
    en_lines = [f"- {n['title']} ({n.get('source','')})" for n in en_news if "error" not in n]

    # 오늘 테제도 컨텍스트로 활용
    thesis_ctx = get_all_today() or ""

    context = (
        f"[한국 뉴스]\n" + "\n".join(ko_lines) +
        f"\n\n[글로벌 뉴스]\n" + "\n".join(en_lines) +
        (f"\n\n[오늘의 테제]\n{thesis_ctx[:1500]}" if thesis_ctx else "")
    )

    send_typing(chat_id)
    report = ask_claude(
        f"""'{topic}'에 대해 심층 리서치 보고서를 작성해줘.

구성:
1. 핵심 현황 (2~3문장)
2. 주요 드라이버 (bullet 3~4개)
3. 리스크 & 기회 요인
4. 결론 및 시사점

뉴스와 테제 데이터를 기반으로 분석하되, 투자 관점에서 실질적으로 유용한 내용으로.""",
        context=context,
        model="claude-sonnet-4-6",
        system_extra="경제·금융 리서치 애널리스트처럼 데이터 기반으로 작성. 마크다운 헤더 사용 가능."
    )

    send(chat_id, f"📋 *리서치 보고서: {topic}*\n\n{report}")
    print(f"[{now_str()}] /research: {topic}")


def cmd_brief(chat_id, topic):
    """빠른 브리핑 (1분 안에)."""
    if not topic:
        send(chat_id, "사용법: `/brief 주제`\n예: `/brief 오늘 환율 동향`")
        return

    send_typing(chat_id)
    from research import search_news, quick_search

    news  = search_news(topic, max_items=4)
    quick = quick_search(topic)

    lines = [f"- {n['title']}" for n in news if "error" not in n]
    context = "\n".join(lines)
    if quick:
        context = f"즉시 답변: {quick}\n\n" + context

    reply = ask_claude(
        f"'{topic}' 에 대해 지금 당장 알아야 할 핵심만 2~3문장으로 브리핑해줘.",
        context=context
    )
    send(chat_id, f"⚡ *브리핑: {topic}*\n\n{reply}")
    print(f"[{now_str()}] /brief: {topic}")


# ── 자유 질문 의도 분류 ───────────────────────────────────────
def classify_intent(text: str) -> tuple[str, str]:
    """질문 의도 분류. (intent, extracted_query) 반환."""
    t = text.lower()

    # 주가/코인 관련
    stock_keywords = ["주가", "주식", "코인", "비트코인", "이더리움", "etf",
                      "나스닥", "s&p", "kospi", "코스피", "달러", "환율",
                      "aapl", "tsla", "nvda", "googl", "amzn"]
    if any(k in t for k in stock_keywords):
        # 티커/종목 추출 시도
        ticker_m = re.search(r"\b([A-Z]{1,5})\b", text)
        kr_name  = next((k for k in ["삼성전자", "하이닉스", "카카오", "네이버", "현대차",
                                      "비트코인", "이더리움"] if k in text), None)
        query = kr_name or (ticker_m.group(1) if ticker_m else text)
        return "stock", query

    # URL 분석
    if re.search(r"https?://\S+", text):
        url = re.search(r"https?://\S+", text).group(0)
        return "url", url

    # 뉴스 요청
    news_keywords = ["뉴스", "최신", "오늘", "어제", "최근", "동향", "현황",
                     "what happened", "latest", "today"]
    if any(k in t for k in news_keywords) and len(text) < 50:
        return "news", text

    # 리서치 요청
    research_keywords = ["분석", "전망", "예측", "리서치", "조사", "연구",
                         "어떻게 될", "왜", "이유", "원인", "영향", "파급"]
    if any(k in t for k in research_keywords):
        return "research", text

    # 기본: 테제 기반 Q&A
    return "chat", text


# ── 명령어 처리 ───────────────────────────────────────────────
HELP_TEXT = """*JAYCE 리서치 봇* 🤖

*테제 명령어*
/today — 오늘 전체 테제 요약
/economy — 경제·투자 테제
/politics — 정치 테제
/culture — 컬처 테제

*리서치 명령어*
/news [키워드] — 최신 뉴스 + AI 요약
/stock [티커/종목] — 주가 조회 + 분석
/url [링크] — 링크 내용 요약
/research [주제] — 심층 리서치 보고서
/brief [주제] — 빠른 브리핑

*자유 질문*
아무 텍스트나 보내면 자동으로 분석합니다.
URL 포함 시 자동 분석, 주가 키워드 시 자동 조회.

/help — 이 메시지"""


def handle_command(chat_id, text):
    parts = text.strip().split(None, 1)
    cmd   = parts[0].lower()
    arg   = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        send(chat_id, HELP_TEXT)
        return

    if cmd == "/today":
        send_typing(chat_id)
        context = get_all_today()
        if not context:
            send(chat_id, "❌ 오늘 테제가 아직 발행되지 않았습니다.")
            return
        reply = ask_claude(
            "오늘 전체 테제의 핵심 포인트를 경제·정치·컬처별로 각 1~2문장으로 정리해줘.",
            context=context, use_history=True
        )
        send(chat_id, reply)
        return

    topic_cmd = {"/economy": "economy", "/politics": "politics", "/culture": "culture"}
    if cmd in topic_cmd:
        topic = topic_cmd[cmd]
        name  = TOPIC_MAP[topic][0]
        send_typing(chat_id)
        text_c, date = load_thesis(topic)
        if not text_c:
            send(chat_id, f"❌ {name} 테제를 찾을 수 없습니다.")
            return
        reply = ask_claude(
            f"{name} 테제의 핵심 테제 한 줄 + 주요 체크포인트 3개를 정리해줘.",
            context=text_c, use_history=True
        )
        send(chat_id, f"*{date} {name}*\n\n{reply}")
        return

    if cmd == "/news":
        cmd_news(chat_id, arg)
        return

    if cmd == "/stock":
        cmd_stock(chat_id, arg)
        return

    if cmd == "/url":
        cmd_url(chat_id, arg)
        return

    if cmd == "/research":
        cmd_research(chat_id, arg)
        return

    if cmd == "/brief":
        cmd_brief(chat_id, arg)
        return

    send(chat_id, f"알 수 없는 명령어입니다: `{cmd}`\n/help 를 입력해보세요.")


def handle_message(chat_id, text):
    """자유 질문 — 의도 분류 후 라우팅."""
    intent, query = classify_intent(text)
    print(f"[{now_str()}] 의도: {intent} | 쿼리: {query[:40]}")

    if intent == "stock":
        cmd_stock(chat_id, query)
    elif intent == "url":
        cmd_url(chat_id, query)
    elif intent == "news":
        cmd_news(chat_id, query)
    elif intent == "research":
        cmd_research(chat_id, query)
    else:
        send_typing(chat_id)
        context = get_all_today() or ""
        reply = ask_claude(text, context=context, use_history=True)
        send(chat_id, reply)


# ── 폴링 루프 ─────────────────────────────────────────────────
def main():
    print(f"[{now_str()}] JAYCE 봇 시작 (chat_id={ALLOWED_CHAT_ID})", flush=True)
    offset = 0

    while True:
        try:
            result = tg("getUpdates", http_timeout=35,
                        offset=offset, timeout=30,
                        allowed_updates=["message"])

            for update in result.get("result", []):
                offset = update["update_id"] + 1
                msg    = update.get("message", {})
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text    = msg.get("text", "").strip()

                if chat_id != ALLOWED_CHAT_ID:
                    print(f"[{now_str()}] 차단된 chat_id: {chat_id}", flush=True)
                    continue

                if not text:
                    continue

                print(f"[{now_str()}] 수신: {text[:60]}", flush=True)

                if text.startswith("/"):
                    handle_command(chat_id, text)
                else:
                    handle_message(chat_id, text)

        except KeyboardInterrupt:
            print("\n봇 종료")
            break
        except urllib.error.URLError as e:
            print(f"[{now_str()}] 네트워크 오류: {e} — 10초 후 재시도", flush=True)
            time.sleep(10)
        except Exception as e:
            print(f"[{now_str()}] 오류: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
