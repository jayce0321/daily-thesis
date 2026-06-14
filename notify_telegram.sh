#!/bin/bash
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-5066621346}"
DATE=$(date +"%Y.%m.%d")

TEXT="📊 Daily Thesis | ${DATE}

\"인플레이션의 마지막 야생 변수가 길들여지려 한다\"

이란 평화협정 가시화로 유가라는 통제 불가능했던 변수가 처음으로 예측 가능한 경로에 들어섰다. 3일 뒤 Warsh 첫 FOMC가 점도표로 답을 써야 한다.

━━━━━━━━━━━━
📌 핵심 지표
• WTI 유가: \$85 ▼2.0%
• 연준 금리인상 확률: 52% (1주 전 25%)
• 미 10년물: 4.55%
• GS 첫 인하 시점: 2027년

━━━━━━━━━━━━
✅ 이번 주 체크리스트
• 6/17 FOMC 점도표 — 2026년 인하 점 여부
• 이란 협정 공식 서명 여부
• Warsh 기자회견 톤

본 자료는 투자 권유가 아닙니다."

RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"${CHAT_ID}\",\"text\":$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" <<< "$TEXT")}")

if echo "$RESPONSE" | grep -q '"ok":true'; then
  echo "✅ 전송 완료"
else
  echo "❌ 전송 실패:"
  echo "$RESPONSE"
fi
