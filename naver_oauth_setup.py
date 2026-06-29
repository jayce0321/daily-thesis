#!/usr/bin/env python3
"""
Naver Blog OAuth 초기 설정 스크립트 — 1회만 실행
목적: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET / NAVER_REFRESH_TOKEN 획득

사전 준비:
  1. https://developers.naver.com/apps/#/register 에서 앱 등록
  2. 앱 유형: WEB 서비스
  3. 사용 API: "블로그 포스팅" 체크
  4. Callback URL: http://localhost:8080/callback 등록
  5. Client ID / Client Secret 복사

실행:
  python naver_oauth_setup.py
"""

import urllib.parse
import urllib.request
import json
import http.server
import threading
import webbrowser
import sys

REDIRECT_URI = "http://localhost:8080/callback"


def main():
    print("=" * 54)
    print("  JAYCE 데일리 테제 — Naver Blog OAuth 초기 설정")
    print("=" * 54)
    print()
    print("사전 준비 (아직 안 하셨다면 먼저 해주세요):")
    print("  1. https://developers.naver.com/apps/#/register")
    print("  2. 앱 유형: WEB 서비스")
    print("  3. 사용 API: '블로그 포스팅' 체크")
    print("  4. Callback URL: http://localhost:8080/callback")
    print()

    client_id = input("Naver Client ID: ").strip()
    client_secret = input("Naver Client Secret: ").strip()

    if not client_id or not client_secret:
        print("\n❌ Client ID와 Secret이 필요합니다.")
        sys.exit(1)

    # ── 인증 코드 수신용 로컬 서버 ──────────────────────────────
    code_box = [None]

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code_box[0] = qs.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "<h2 style='font-family:sans-serif'>✅ 완료! 이 창을 닫고 터미널을 확인하세요.</h2>"
            self.wfile.write(msg.encode("utf-8"))

        def log_message(self, fmt, *args):
            pass  # 서버 로그 억제

    server = http.server.HTTPServer(("localhost", 8080), _Handler)
    t = threading.Thread(target=server.handle_request)
    t.daemon = True
    t.start()

    # ── OAuth 인증 URL ───────────────────────────────────────────
    auth_url = (
        "https://nid.naver.com/oauth2.0/authorize?"
        + urllib.parse.urlencode({
            "response_type": "code",
            "client_id":     client_id,
            "redirect_uri":  REDIRECT_URI,
            "state":         "JAYCE_DAILY",
        })
    )
    print("\n브라우저에서 네이버 로그인 창이 열립니다...")
    webbrowser.open(auth_url)
    print(f"자동으로 열리지 않으면 직접 접속:\n{auth_url}\n")

    t.join(timeout=120)
    code = code_box[0]

    if not code:
        print("❌ 인증 코드를 받지 못했습니다. (120초 초과 또는 취소)")
        print("   → Callback URL이 http://localhost:8080/callback 인지 확인하세요.")
        sys.exit(1)

    # ── Authorization Code → Token 교환 ─────────────────────────
    token_body = urllib.parse.urlencode({
        "grant_type":    "authorization_code",
        "client_id":     client_id,
        "client_secret": client_secret,
        "code":          code,
        "state":         "JAYCE_DAILY",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://nid.naver.com/oauth2.0/token",
        data=token_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tokens = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"\n❌ 토큰 교환 실패: {e}")
        sys.exit(1)

    if "error" in tokens:
        print(f"\n❌ 오류: {tokens.get('error_description', tokens.get('error'))}")
        sys.exit(1)

    access_token  = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")

    print("\n✅ 토큰 발급 완료!\n")

    # ── 블로그 접근 권한 확인 ────────────────────────────────────
    print("블로그 API 접근 권한 확인 중...")
    test_body = urllib.parse.urlencode({
        "title":    "JAYCE 블로그 자동화 연동 테스트",
        "contents": "<p>자동화 연동 확인용 테스트 포스팅입니다. 바로 삭제해주세요.</p>",
        "tags":     "테스트",
    }).encode("utf-8")
    test_req = urllib.request.Request(
        "https://openapi.naver.com/blog/writePost.json",
        data=test_body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(test_req, timeout=15) as r:
            test_resp = json.loads(r.read().decode("utf-8"))
        if test_resp.get("resultcode") == "00":
            blog_url = test_resp.get("blogUrl", "")
            print(f"  ✅ 테스트 포스팅 성공: {blog_url}")
            print("  → 네이버 블로그에서 테스트 글을 직접 삭제해주세요.")
        else:
            print(f"  ⚠️  포스팅 응답 이상: {test_resp}")
            print("  → 앱 등록 시 '블로그 포스팅' 권한을 체크했는지 확인하세요.")
    except Exception as e:
        print(f"  ⚠️  테스트 실패: {e}")
        print("  → 앱 권한 설정을 다시 확인하세요.")

    # ── 환경변수 출력 ─────────────────────────────────────────────
    print()
    print("=" * 54)
    print("  아래 값을 GitHub Secrets + Railway 환경변수에 저장하세요")
    print("=" * 54)
    print(f"  NAVER_CLIENT_ID     = {client_id}")
    print(f"  NAVER_CLIENT_SECRET = {client_secret}")
    print(f"  NAVER_REFRESH_TOKEN = {refresh_token}")
    print("=" * 54)
    print()
    print("GitHub Secrets 저장 위치:")
    print("  https://github.com/jayce0321/daily-thesis/settings/secrets/actions")
    print()
    print("Railway 환경변수 저장 위치:")
    print("  Railway 대시보드 → 서비스 → Variables 탭")
    print()
    print("⚠️  Refresh Token은 만료되지 않지만, 앱 권한 변경 시 재발급 필요")
    print("   재발급이 필요하면 이 스크립트를 다시 실행하세요.")


if __name__ == "__main__":
    main()
