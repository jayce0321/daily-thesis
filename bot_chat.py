#!/usr/bin/env python3
"""
JAYCE 데일리 테제 채팅봇
텔레그램 폴링 방식으로 메시지를 받아 Claude API로 답변
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import re
import glob
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 환경 변수 ─────────────────────────────────────────────────
REPO_DIR   = Path(__file__).parent.resolve()
ENV_FILE   = REPO_DIR / ".env"

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

# ── 텔레그램 헬퍼 ─────────────────────────────────────────────
def tg(method, http_timeout=15, **params):
    data = json.dumps(params).encode()
    req  = urllib.request.Request(
        f"{TG_API}/{method}", data=data,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=http_timeout) as r:
        return json.loads(r.read())

def send(chat_id, text, parse_mode="Markdown"):
    try:
        tg("sendMessage", chat_id=chat_id, text=text,
           parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception as e:
        print(f"[send error] {e}")
        try:
            tg("sendMessage", chat_id=chat_id, text=text)
        except Exception:
            pass

def send_typing(chat_id):
    try:
        tg("sendChatAction", chat_id=chat_id, action="typing")
    except Exception:
        pass

# ── 테제 콘텐츠 로드 ──────────────────────────────────────────
TOPIC_MAP = {
    "economy":  ("경제·투자", ""),
    "politics": ("정치",     "-politics"),
    "culture":  ("컬처",     "-culture"),
}

def load_thesis(topic="economy", date_str=None):
    """HTML에서 텍스트 추출. date_str 없으면 최신 파일 사용."""
    suffix = TOPIC_MAP[topic][1]
    if date_str:
        pattern = str(REPO_DIR / f"{date_str}{suffix}.html")
    else:
        files = sorted(glob.glob(str(REPO_DIR / f"*{suffix}.html")))
        # index.html, politics.html 등 날짜 없는 파일 제외
        files = [f for f in files if re.search(r'\d{4}-\d{2}-\d{2}', f)]
        if not files:
            return None, None
        pattern = files[-1]

    path = Path(pattern)
    if not path.exists():
        return None, None

    html  = path.read_text(encoding="utf-8")
    date  = re.search(r'(\d{4}-\d{2}-\d{2})', path.name)
    date  = date.group(1) if date else "최근"

    # 텍스트 추출
    html  = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html  = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text  = re.sub(r'<[^>]+>', ' ', html)
    text  = re.sub(r'\s+', ' ', text).strip()
    return text[:6000], date

def get_all_today():
    """오늘 날짜 기준 모든 토픽 요약."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    parts = []
    for topic, (name, suffix) in TOPIC_MAP.items():
        text, date = load_thesis(topic, today)
        if text:
            parts.append(f"[{name}]\n{text[:1500]}")
    return "\n\n".join(parts) if parts else None

# ── Claude API ────────────────────────────────────────────────
def ask_claude(user_msg, context, topic_name="오늘의 테제"):
    system = f"""당신은 JAYCE 데일리 테제 봇입니다.
Jaeho Lee의 개인 경제·정치·컬처 분석 브리핑 서비스의 AI 어시스턴트입니다.

아래는 {topic_name} 내용입니다:
---
{context}
---

답변 규칙:
- 테제 내용을 기반으로 깊이 있는 인사이트를 제공하세요
- 투자 조언은 하지 않되, 시장 해석과 관점은 제시하세요
- 핵심을 짧고 명확하게 (3~5문장 권장)
- 한국어로 답변
- 추가 질문을 유도하는 문장으로 마무리"""

    data = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    return result["content"][0]["text"]

# ── 명령어 처리 ───────────────────────────────────────────────
HELP_TEXT = """*JAYCE 데일리 테제 봇* 🤖

*명령어*
/today — 오늘 전체 테제 요약
/economy — 경제·투자 테제
/politics — 정치 테제
/culture — 컬처 테제
/help — 도움말

*자유 질문*
테제 내용에 대한 질문을 자유롭게 입력하세요.
예: "오늘 연준 관련 핵심 포인트가 뭐야?"
예: "이란 협정이 원유 시장에 미치는 영향은?"
"""

def handle_command(chat_id, cmd):
    if cmd in ("/start", "/help"):
        send(chat_id, HELP_TEXT)
        return

    if cmd == "/today":
        send_typing(chat_id)
        context = get_all_today()
        if not context:
            send(chat_id, "❌ 오늘 테제가 아직 발행되지 않았습니다.")
            return
        reply = ask_claude("오늘 전체 테제의 핵심 포인트를 3가지로 정리해줘", context, "오늘 전체 테제")
        send(chat_id, reply)
        return

    topic_cmd = {"/economy": "economy", "/politics": "politics", "/culture": "culture"}
    if cmd in topic_cmd:
        topic   = topic_cmd[cmd]
        name    = TOPIC_MAP[topic][0]
        send_typing(chat_id)
        text, date = load_thesis(topic)
        if not text:
            send(chat_id, f"❌ {name} 테제를 찾을 수 없습니다.")
            return
        reply = ask_claude(f"{name} 테제의 핵심 테제와 주요 시사점을 요약해줘", text, f"{date} {name} 테제")
        send(chat_id, f"📊 *{date} {name} 테제 요약*\n\n{reply}")
        return

    send(chat_id, "알 수 없는 명령어입니다. /help 를 입력해보세요.")

def handle_message(chat_id, text):
    """자유 질문 처리 — 가장 최신 전체 컨텍스트 기반."""
    send_typing(chat_id)
    context = get_all_today()
    if not context:
        # 오늘 없으면 최신 경제 테제라도
        context, date = load_thesis("economy")
        if not context:
            send(chat_id, "❌ 참고할 테제 데이터가 없습니다.")
            return
    try:
        reply = ask_claude(text, context)
        send(chat_id, reply)
    except Exception as e:
        send(chat_id, f"⚠️ 오류가 발생했습니다: {e}")

# ── 폴링 루프 ─────────────────────────────────────────────────
def main():
    print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] JAYCE 봇 시작 (chat_id={ALLOWED_CHAT_ID})")
    offset = 0

    while True:
        try:
            result = tg("getUpdates", http_timeout=35, offset=offset, timeout=30, allowed_updates=["message"])
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                msg    = update.get("message", {})
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text    = msg.get("text", "").strip()

                if chat_id != ALLOWED_CHAT_ID:
                    print(f"[차단] 허용되지 않은 chat_id: {chat_id}")
                    continue

                if not text:
                    continue

                print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] 메시지: {text[:60]}")

                if text.startswith("/"):
                    cmd = text.split()[0].lower()
                    handle_command(chat_id, cmd)
                else:
                    handle_message(chat_id, text)

        except KeyboardInterrupt:
            print("\n봇 종료")
            break
        except urllib.error.URLError as e:
            print(f"[네트워크 오류] {e} — 10초 후 재시도")
            time.sleep(10)
        except Exception as e:
            print(f"[오류] {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
