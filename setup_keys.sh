#!/bin/bash
# 시크릿 키체인 관리 스크립트
# 사용법:
#   ./setup_keys.sh set    — 키 입력 후 Keychain에 저장
#   ./setup_keys.sh env    — Keychain에서 .env 생성
#   ./setup_keys.sh check  — 저장된 키 상태 확인

SERVICE="jayce-daily-thesis"

_save() {
  local key="$1" val="$2"
  security delete-generic-password -s "$SERVICE" -a "$key" 2>/dev/null || true
  security add-generic-password -s "$SERVICE" -a "$key" -w "$val"
}

_load() {
  security find-generic-password -s "$SERVICE" -a "$1" -w 2>/dev/null
}

case "${1:-env}" in

  set)
    echo "=== Jayce Daily Thesis — 키 등록 ==="
    echo ""
    read -p "ANTHROPIC_API_KEY: " -r ANTHROPIC_KEY
    _save ANTHROPIC_API_KEY "$ANTHROPIC_KEY"
    echo "✅ ANTHROPIC_API_KEY 저장"

    read -p "TELEGRAM_BOT_TOKEN: " -r TG_TOKEN
    _save TELEGRAM_BOT_TOKEN "$TG_TOKEN"
    echo "✅ TELEGRAM_BOT_TOKEN 저장"

    echo ""
    echo "✅ 키체인 저장 완료. 이제 ./setup_keys.sh env 로 .env 생성하세요."
    ;;

  env)
    ANTHROPIC_KEY=$(_load ANTHROPIC_API_KEY)
    TG_TOKEN=$(_load TELEGRAM_BOT_TOKEN)

    if [ -z "$ANTHROPIC_KEY" ] || [ -z "$TG_TOKEN" ]; then
      echo "❌ 키체인에 키가 없습니다. 먼저 ./setup_keys.sh set 을 실행하세요."
      exit 1
    fi

    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    cat > "$SCRIPT_DIR/.env" <<EOF
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
TELEGRAM_BOT_TOKEN=${TG_TOKEN}
EOF
    echo "✅ .env 생성 완료"
    ;;

  check)
    echo "=== 키체인 상태 확인 ==="
    for KEY in ANTHROPIC_API_KEY TELEGRAM_BOT_TOKEN; do
      VAL=$(_load "$KEY")
      if [ -n "$VAL" ]; then
        echo "✅ $KEY: ${VAL:0:12}..."
      else
        echo "❌ $KEY: 없음"
      fi
    done

    echo ""
    echo "=== 텔레그램 봇 상태 ==="
    TG_TOKEN=$(_load TELEGRAM_BOT_TOKEN)
    if [ -n "$TG_TOKEN" ]; then
      RESULT=$(curl -s "https://api.telegram.org/bot${TG_TOKEN}/getMe")
      if echo "$RESULT" | grep -q '"ok":true'; then
        USERNAME=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['username'])")
        echo "✅ 봇 정상: @${USERNAME}"
      else
        echo "❌ 봇 오류: $RESULT"
      fi
    fi
    ;;

  *)
    echo "사용법: ./setup_keys.sh [set|env|check]"
    exit 1
    ;;
esac
