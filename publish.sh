#!/bin/bash
# 데일리 테제 자동 발행 스크립트
# 사용법: ./publish.sh [날짜]  예) ./publish.sh 2026-06-15
# 날짜 생략시 오늘 날짜 자동 사용

set -e

DATE=${1:-$(date +"%Y-%m-%d")}
DATE_KR=$(date -j -f "%Y-%m-%d" "$DATE" +"%Y.%m.%d" 2>/dev/null || date -d "$DATE" +"%Y.%m.%d")
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-5066621346}"

echo "📝 [$DATE] 발행 시작..."

# 1. HTML 파일 존재 확인
if [ ! -f "$REPO_DIR/${DATE}.html" ]; then
  echo "❌ ${DATE}.html 파일이 없습니다."
  echo "   먼저 분석 HTML 파일을 생성해주세요."
  exit 1
fi

# 2. index.html에 새 글 추가
python3 - <<PYEOF
import re

date = "$DATE"
date_kr = "$DATE_KR"

with open("$REPO_DIR/index.html", "r") as f:
    content = f.read()

# 이미 있으면 스킵
if f'href="{date}.html"' in content:
    print(f"⚠️  {date} 항목이 이미 index에 있습니다.")
    exit(0)

# 제목을 HTML 파일에서 추출
with open(f"$REPO_DIR/{date}.html", "r") as f:
    html = f.read()

title_match = re.search(r'<title>(.*?)</title>', html)
h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)

title = "데일리 테제"
if h1_match:
    raw = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip().replace('\n', ' ')
    title = ' '.join(raw.split())

new_entry = f'''      <a class="post-item" href="{date}.html">
        <div>
          <div class="post-title">{title}</div>
          <div class="post-sub">데일리 테제 분석</div>
        </div>
        <div class="post-date">{date_kr}</div>
      </a>'''

content = content.replace(
    '<div class="post-list">',
    '<div class="post-list">\n' + new_entry
)

with open("$REPO_DIR/index.html", "w") as f:
    f.write(content)

print(f"✅ index.html 업데이트 완료")
PYEOF

# 3. Git 커밋 & 푸시
cd "$REPO_DIR"
git add "${DATE}.html" index.html
git commit -m "데일리 테제 ${DATE_KR}"
git push origin main
echo "🚀 GitHub Pages 게시 완료"
echo "   → https://jayce0321.github.io/daily-thesis/${DATE}.html"

# 4. 텔레그램 알림
bash "$REPO_DIR/notify_telegram.sh"
