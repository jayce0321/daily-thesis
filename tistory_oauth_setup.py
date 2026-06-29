#!/usr/bin/env python3
"""
Tistory Blog OAuth 초기 설정 스크립트 — 1회만 실행
목적: TISTORY_ACCESS_TOKEN + TISTORY_BLOG_NAME 획득

사전 준비:
  1. https://www.tistory.com/guide/api/manage/register 에서 앱 등록
  2. 앱 이름: JAYCE 데일리 테제 (자유)
  3. 서비스 URL: https://jayce0321.github.io/daily-thesis
  4. Callback URL: http://localhost:8080/callback
  5. App ID + Secret Key 복사

실행:
  python tistory_oauth_setup.py
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
    print("=" * 56)
    print("  JAYCE 데일리 테제 — Tistory OAuth 초기 설정")
    print("=" * 56)
    print()
    print("사전 준비 (아직 안 하셨다면 먼저 해주세요):")
    print("  1. https://www.tistory.com/guide/api/manage/register")
    print("  2. 앱 이름: JAYCE 데일리 테제")
    print("  3. 서비스 URL: https://jayce0321.github.io/daily-thesis")
    print("  4. Callback URL: http://localhost:8080/callback")
    print()

    client_id = input("Tistory App ID: ").strip()
    client_secret = input("Tistory Secret Key: ").strip()

    if not client_id or not client_secret:
        print("\n❌ App ID와 Secret Key가 필요합니다.")
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
            pass

    server = http.server.HTTPServer(("localhost", 8080), _Handler)
    t = threading.Thread(target=server.handle_request)
    t.daemon = True
    t.start()

    # ── OAuth 인증 URL ───────────────────────────────────────────
    auth_url = (
        "https://www.tistory.com/oauth/authorize?"
        + urllib.parse.urlencode({
            "client_id":     client_id,
            "redirect_uri":  REDIRECT_URI,
            "response_type": "code",
        })
    )
    print("\n브라우저에서 티스토리 로그인 창이 열립니다...")
    webbrowser.open(auth_url)
    print(f"자동으로 열리지 않으면 직접 접속:\n{auth_url}\n")

    t.join(timeout=120)
    code = code_box[0]

    if not code:
        print("❌ 인증 코드를 받지 못했습니다. (120초 초과 또는 취소)")
        print("   → Callback URL이 http://localhost:8080/callback 인지 확인하세요.")
        sys.exit(1)

    # ── Authorization Code → Access Token 교환 ──────────────────
    token_url = (
        "https://www.tistory.com/oauth/access_token?"
        + urllib.parse.urlencode({
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  REDIRECT_URI,
            "code":          code,
            "grant_type":    "authorization_code",
        })
    )
    try:
        req = urllib.request.Request(token_url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8")
        qs = urllib.parse.parse_qs(raw)
        access_token = qs.get("access_token", [None])[0]
    except Exception as e:
        print(f"\n❌ 토큰 교환 실패: {e}")
        sys.exit(1)

    if not access_token:
        print(f"\n❌ 토큰 파싱 실패. 응답: {raw}")
        sys.exit(1)

    # ── 블로그 정보 조회 ─────────────────────────────────────────
    blog_name = ""
    print("\n블로그 정보 확인 중...")
    info_url = (
        "https://www.tistory.com/apis/blog/info?"
        + urllib.parse.urlencode({"access_token": access_token, "output": "json"})
    )
    try:
        with urllib.request.urlopen(info_url, timeout=10) as r:
            info = json.loads(r.read().decode("utf-8"))
        blogs_raw = (info.get("tistory", {})
                         .get("item", {})
                         .get("blogs", {})
                         .get("blog", []))
        if isinstance(blogs_raw, dict):
            blogs_raw = [blogs_raw]
        if blogs_raw:
            print("  보유 블로그 목록:")
            for b in blogs_raw:
                b_name = b.get("name", "")
                b_url  = b.get("url", "")
                print(f"    - {b_name}  ({b_url})")
            blog_name = blogs_raw[0].get("name", "")
            if len(blogs_raw) > 1:
                chosen = input(f"\n사용할 블로그 이름 [{blog_name}]: ").strip()
                if chosen:
                    blog_name = chosen
        else:
            print("  ⚠️  블로그 목록을 가져오지 못했습니다.")
    except Exception as e:
        print(f"  ⚠️  블로그 정보 조회 실패: {e}")

    if not blog_name:
        blog_name = input("티스토리 블로그 이름 (예: myblog → myblog.tistory.com): ").strip()

    # ── 테스트 포스팅 (비공개) ───────────────────────────────────
    print("\n테스트 포스팅 중 (비공개)...")
    test_body = urllib.parse.urlencode({
        "access_token": access_token,
        "output":       "json",
        "blogName":     blog_name,
        "title":        "[JAYCE 자동화 연동 테스트 — 삭제해주세요]",
        "content":      "<p>자동화 연동 확인용 테스트 포스팅입니다. 바로 삭제해주세요.</p>",
        "visibility":   "0",   # 0=비공개
        "tag":          "테스트",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://www.tistory.com/apis/post/write",
            data=test_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            tr = json.loads(r.read().decode("utf-8"))
        ts = tr.get("tistory", {})
        if str(ts.get("status")) == "200":
            print(f"  ✅ 테스트 포스팅 성공!")
            print(f"     → 티스토리 관리자에서 비공개 글을 삭제해주세요.")
        else:
            print(f"  ⚠️  포스팅 응답 이상: {tr}")
    except Exception as e:
        print(f"  ⚠️  테스트 실패: {e}")

    # ── 결과 출력 ────────────────────────────────────────────────
    print()
    print("=" * 56)
    print("  아래 값을 GitHub Secrets + Railway 환경변수에 저장하세요")
    print("=" * 56)
    print(f"  TISTORY_ACCESS_TOKEN = {access_token}")
    print(f"  TISTORY_BLOG_NAME    = {blog_name}")
    print("=" * 56)
    print()
    print("GitHub Secrets 저장 위치:")
    print("  https://github.com/jayce0321/daily-thesis/settings/secrets/actions")
    print()
    print("Railway 환경변수 저장 위치:")
    print("  Railway 대시보드 → 서비스 → Variables 탭")
    print()
    print("⚠️  Tistory Access Token은 만료되지 않습니다.")
    print("   앱 삭제 또는 권한 변경 시에만 재발급 필요.")


if __name__ == "__main__":
    main()
