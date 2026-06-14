#!/usr/bin/env python3
"""
데일리 테제 자동화 파이프라인
1. 오늘 주요 뉴스 수집
2. Claude API로 테제 분석 생성
3. HTML 파일 작성
4. GitHub Pages 게시 + 텔레그램 알림
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

# ── 설정 ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8962117729:AAE0P63U6ao_7RWW485-XGXLhBPUvhd689k")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5066621346")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
IS_CI = os.environ.get("GITHUB_ACTIONS") == "true"

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
TODAY_KR = datetime.now(KST).strftime("%Y.%m.%d")

# ─────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] {msg}")

# ── 1. 뉴스 수집 ─────────────────────────────────────────────
def fetch_news():
    log("뉴스 수집 중...")
    queries = [
        "글로벌 금융시장 오늘 뉴스 매크로",
        "Federal Reserve FOMC market news today",
        "미국 주식시장 경제지표 today",
    ]
    articles = []
    for q in queries:
        try:
            encoded = urllib.parse.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                content = r.read().decode("utf-8")
            import re
            items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
            for item in items[:5]:
                title = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item)
                if not title:
                    title = re.search(r'<title>(.*?)</title>', item)
                if title:
                    articles.append(title.group(1).strip())
        except Exception as e:
            log(f"뉴스 수집 오류 (무시): {e}")
    seen = set()
    unique = []
    for a in articles:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    log(f"뉴스 {len(unique)}건 수집 완료")
    return unique[:20]

# ── 2. Claude API 호출 (tool_use로 JSON 보장) ────────────────
def call_claude(news_headlines):
    log("Claude API 호출 중...")
    headlines_text = "\n".join(f"- {h}" for h in news_headlines)

    tool_def = {
        "name": "save_thesis",
        "description": "데일리 테제 분석 결과를 저장한다",
        "input_schema": {
            "type": "object",
            "properties": {
                "thesis_title": {"type": "string", "description": "테제 제목 (따옴표 포함, 20자 내외)"},
                "one_line": {"type": "string", "description": "한 줄 핵심 요약"},
                "why_important": {"type": "string", "description": "왜 중요한가 (배경 설명 2~3문장)"},
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                            "meaning": {"type": "string"}
                        },
                        "required": ["label", "value", "meaning"]
                    },
                    "description": "숫자 근거 3~5개"
                },
                "scenario_a": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "points": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["title", "points"]
                },
                "scenario_b": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
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
                            "desc": {"type": "string"}
                        },
                        "required": ["title", "desc"]
                    },
                    "description": "투자자 체크리스트 2~3개"
                },
                "closing": {"type": "string", "description": "마무리 한 줄"}
            },
            "required": ["thesis_title", "one_line", "why_important", "metrics",
                         "scenario_a", "scenario_b", "checklist", "closing"]
        }
    }

    data = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 2000,
        "tools": [tool_def],
        "tool_choice": {"type": "tool", "name": "save_thesis"},
        "messages": [{
            "role": "user",
            "content": f"""오늘({TODAY_KR}) 뉴스를 바탕으로 시장을 관통하는 핵심 테제 하나를 도출해줘.
단순 뉴스 나열 금지. 하나의 테제로 오늘 시장을 설명해야 한다.

수집된 뉴스:
{headlines_text}"""
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

    # tool_use 블록에서 input 추출 — 항상 유효한 JSON
    for block in result["content"]:
        if block.get("type") == "tool_use":
            analysis = block["input"]
            log("Claude 분석 완료")
            return analysis

    raise ValueError(f"tool_use 응답 없음: {result}")

# ── 2b. SVG 이미지 생성 (Python 직접 생성 — 100% 안정) ──────
import html as _html
import hashlib

def generate_svgs(analysis):
    log("SVG 이미지 생성 중...")
    metrics  = analysis.get("metrics", [])
    title    = analysis.get("thesis_title", "")
    one_line = analysis.get("one_line", "")

    # ── 커버 SVG ─────────────────────────────────────────────
    # 제목 해시로 색상 시드 결정 (매일 다른 패턴)
    seed = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
    def _c(base, offset):
        v = (base + offset) % 360
        return v

    safe_title = _html.escape(title[:34] + ("…" if len(title) > 34 else ""))
    safe_oneline = _html.escape(one_line[:60] + ("…" if len(one_line) > 60 else ""))

    # 도형 파라미터 (시드 기반)
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
  <!-- 배경 광원 -->
  <circle cx="{cx1}" cy="{cy1}" r="160" fill="#1a3a5c" filter="url(#blur)" opacity="0.6"/>
  <circle cx="{cx2}" cy="{cy2}" r="120" fill="#1a2a10" filter="url(#blur)" opacity="0.4"/>
  <!-- 기하 도형 -->
  <circle cx="{cx1}" cy="{cy1}" r="90" fill="none" stroke="#e8b84b" stroke-width="1" opacity="0.25"/>
  <circle cx="{cx1}" cy="{cy1}" r="50" fill="none" stroke="#e8b84b" stroke-width="0.5" opacity="0.4"/>
  <circle cx="{cx2}" cy="{cy2}" r="70" fill="none" stroke="#5b8dee" stroke-width="1" opacity="0.3"/>
  <circle cx="{cx3}" cy="{cy3}" r="40" fill="#e8b84b" opacity="0.06"/>
  <line x1="{cx1-100}" y1="{cy1+30}" x2="{cx2+50}" y2="{cy2-40}" stroke="#e8b84b" stroke-width="0.5" opacity="0.2"/>
  <line x1="0" y1="310" x2="900" y2="310" stroke="#252b3b" stroke-width="1"/>
  <!-- 텍스트 -->
  <text x="870" y="32" text-anchor="end" fill="#4a5269" font-size="12" letter-spacing="1">{TODAY_KR}</text>
  <text x="48" y="240" fill="#e2e6f0" font-size="22" font-weight="700" opacity="0.95">{safe_title}</text>
  <text x="48" y="272" fill="#7a8299" font-size="13">{safe_oneline}</text>
  <text x="48" y="332" fill="#e8b84b" font-size="10" letter-spacing="3" font-weight="600">DAILY THESIS</text>
</svg>'''

    # ── 차트 SVG ─────────────────────────────────────────────
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
        # 바 길이: 인덱스 기반 상대적 너비 (뒤로 갈수록 약간 줄어들어 자연스럽게)
        w   = max(60, max_bar - i * (max_bar // (len(metrics) + 1)))
        lbl = _html.escape(m.get("label", "")[:22])
        val = _html.escape(m.get("value", ""))
        bars += f'''  <text x="{pad_l - 10}" y="{y + bar_h//2 + 5}" text-anchor="end" fill="#7a8299" font-size="12">{lbl}</text>
  <rect x="{pad_l}" y="{y}" width="{w}" height="{bar_h}" fill="{col}" rx="4" opacity="0.85"/>
  <text x="{pad_l + w + 8}" y="{y + bar_h//2 + 5}" fill="#e2e6f0" font-size="13" font-weight="700">{val}</text>\n'''

    chart_svg = f'''<svg viewBox="0 0 800 {chart_h}" xmlns="http://www.w3.org/2000/svg" font-family="'Apple SD Gothic Neo','Noto Sans KR',sans-serif">
  <rect width="800" height="{chart_h}" fill="#161a23"/>
  <text x="20" y="26" fill="#4a5269" font-size="11" letter-spacing="2">KEY METRICS</text>
{bars}</svg>'''

    log(f"SVG 생성 완료 (커버:{len(cover_svg)}자, 차트:{len(chart_svg)}자)")
    return cover_svg, chart_svg

# ── 3. HTML 생성 ─────────────────────────────────────────────
def build_html(a, cover_svg="", chart_svg=""):
    metrics_rows = ""
    for m in a.get("metrics", []):
        metrics_rows += f"""
            <tr>
              <td>{m['label']}</td>
              <td>{m['value']}</td>
              <td>{m['meaning']}</td>
            </tr>"""

    checklist_items = ""
    for c in a.get("checklist", []):
        checklist_items += f"""
        <div class="checklist-item">
          <div class="check-box"></div>
          <div>
            <div class="title">{c['title']}</div>
            <div class="desc">{c['desc']}</div>
          </div>
        </div>"""

    sa = a.get("scenario_a", {})
    sb = a.get("scenario_b", {})
    sa_points = "".join(f"<li>{p}</li>" for p in sa.get("points", []))
    sb_points = "".join(f"<li>{p}</li>" for p in sb.get("points", []))

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>데일리 테제 | {TODAY_KR}</title>
  <style>
    :root {{
      --bg:#0d0f14;--surface:#161a23;--border:#252b3b;
      --accent:#e8b84b;--accent2:#5b8dee;--red:#e05c5c;
      --green:#4caf80;--text:#e2e6f0;--muted:#7a8299;--tag-bg:#1e2435;
    }}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--text);font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;line-height:1.75}}
    .hero{{position:relative;overflow:hidden;min-height:400px;display:flex;flex-direction:column;justify-content:flex-end;padding:56px 48px 48px;background:linear-gradient(160deg,#0d1a2e 0%,#0d0f14 60%)}}
    .hero::before{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 20% 80%,rgba(232,184,75,.08) 0%,transparent 50%),radial-gradient(circle at 80% 20%,rgba(91,141,238,.1) 0%,transparent 50%)}}
    .hero-eyebrow{{display:flex;align-items:center;gap:12px;margin-bottom:20px;position:relative}}
    .hero-date{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
    .hero-dot{{width:4px;height:4px;border-radius:50%;background:var(--accent)}}
    .hero-label{{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);font-weight:600}}
    .hero-tags{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px;position:relative}}
    .tag{{font-size:11px;padding:3px 10px;border-radius:20px;background:var(--tag-bg);border:1px solid var(--border);color:var(--muted)}}
    .hero h1{{font-size:clamp(22px,4vw,38px);font-weight:700;line-height:1.3;position:relative;max-width:800px}}
    .hero h1 em{{font-style:normal;color:var(--accent)}}
    .hero-sub{{margin-top:16px;font-size:15px;color:var(--muted);max-width:620px;position:relative}}
    .market-banner{{display:flex;border-top:1px solid var(--border);border-bottom:1px solid var(--border);overflow-x:auto;background:var(--surface)}}
    .market-item{{flex:1;min-width:130px;padding:14px 18px;border-right:1px solid var(--border);display:flex;flex-direction:column;gap:4px}}
    .market-item:last-child{{border-right:none}}
    .market-label{{font-size:10px;color:var(--muted);letter-spacing:.1em;text-transform:uppercase}}
    .market-value{{font-size:17px;font-weight:700}}
    .market-change{{font-size:12px}}
    .up{{color:var(--green)}}.down{{color:var(--red)}}.warn{{color:var(--accent)}}
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
    @media(max-width:600px){{.scenario-grid{{grid-template-columns:1fr}}}}
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
  </style>
</head>
<body>

<section class="hero">
  {('<div class="hero-cover">' + cover_svg + '</div>') if cover_svg else ''}
  <div class="hero-eyebrow">
    <span class="hero-date">{TODAY_KR}</span>
    <span class="hero-dot"></span>
    <span class="hero-label">Daily Thesis</span>
  </div>
  <div class="hero-tags">
    <span class="tag">매크로</span><span class="tag">글로벌시장</span><span class="tag">데일리테제</span>
  </div>
  <h1>{a['thesis_title']}</h1>
  <p class="hero-sub">{a['one_line']}</p>
</section>

<div class="container">

  <div class="thesis-block">
    <div class="label">오늘의 핵심 테제</div>
    <p>{a['one_line']}</p>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-number">1</div>
      <h2>왜 이게 중요한가</h2>
    </div>
    <p>{a['why_important']}</p>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-number">2</div>
      <h2>숫자로 보는 근거</h2>
    </div>
    {('<div class="chart-wrap">' + chart_svg + '</div>') if chart_svg else ''}
    <div class="data-table-wrap">
      <table>
        <thead><tr><th>지표</th><th>수치</th><th>의미</th></tr></thead>
        <tbody>{metrics_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-number">3</div>
      <h2>시나리오 분기</h2>
    </div>
    <div class="scenario-grid">
      <div class="scenario-card green">
        <div class="scenario-label">시나리오 A</div>
        <h3>{sa.get('title','')}</h3>
        <ul>{sa_points}</ul>
      </div>
      <div class="scenario-card red">
        <div class="scenario-label">시나리오 B</div>
        <h3>{sb.get('title','')}</h3>
        <ul>{sb_points}</ul>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-number">4</div>
      <h2>이번 주 투자자 체크리스트</h2>
    </div>
    <div class="checklist">{checklist_items}</div>
  </div>

  <div class="callout">
    <p>{a['closing']}</p>
  </div>

</div>
<footer>데일리 테제 분석 · {TODAY_KR} · 본 자료는 투자 권유가 아닙니다</footer>
</body>
</html>"""

# ── 4. 게시 + 알림 ───────────────────────────────────────────
def publish(html_content, analysis):
    html_path = os.path.join(REPO_DIR, f"{TODAY}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    log(f"HTML 저장: {html_path}")

    # index.html 업데이트
    index_path = os.path.join(REPO_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        index = f.read()

    if f'href="{TODAY}.html"' not in index:
        title = analysis['thesis_title']
        new_entry = f"""      <a class="post-item" href="{TODAY}.html">
        <div>
          <div class="post-title">{title}</div>
          <div class="post-sub">{analysis['one_line'][:40]}...</div>
        </div>
        <div class="post-date">{TODAY_KR}</div>
      </a>"""
        index = index.replace(
            '<div class="post-list">',
            '<div class="post-list">\n' + new_entry
        )
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index)
        log("index.html 업데이트 완료")

    # git push (로컬 실행 시만 — Actions는 워크플로우에서 처리)
    if not IS_CI:
        os.chdir(REPO_DIR)
        # 원격 최신 상태 동기화 후 커밋 (Actions와 충돌 방지)
        subprocess.run(["git", "fetch", "origin"], check=True)
        subprocess.run(["git", "reset", "--hard", "origin/main"], check=True)
        # reset 후 파일 다시 저장
        with open(os.path.join(REPO_DIR, f"{TODAY}.html"), "w", encoding="utf-8") as _f:
            _f.write(html_content[0] if isinstance(html_content, tuple) else html_content)
        subprocess.run(["git", "add", f"{TODAY}.html", "index.html"], check=True)
        staged = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if staged.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"데일리 테제 {TODAY_KR}"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
    log("GitHub Pages 게시 완료")
    log(f"→ https://jayce0321.github.io/daily-thesis/{TODAY}.html")

    # Obsidian 저장
    obs_dir = os.path.expanduser("~/Documents/Obsidian/데일리분석/테제")
    os.makedirs(obs_dir, exist_ok=True)
    md_path = os.path.join(obs_dir, f"{TODAY}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"""---
date: {TODAY}
tags: [데일리테제, 매크로]
type: daily-thesis
---

# 데일리 테제 | {TODAY_KR}

## {analysis['thesis_title']}

{analysis['one_line']}

---

### 왜 중요한가
{analysis['why_important']}

### 마무리
{analysis['closing']}
""")
    log(f"Obsidian 저장 완료: {md_path}")

    # 텔레그램
    text = f"""📊 데일리 테제 | {TODAY_KR}

{analysis['thesis_title']}

{analysis['one_line']}

━━━━━━━━━━━━
✅ 체크리스트
""" + "\n".join(f"• {c['title']}" for c in analysis.get('checklist', [])) + f"""

🔗 https://jayce0321.github.io/daily-thesis/{TODAY}.html

본 자료는 투자 권유가 아닙니다."""

    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": text
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
    if result.get("ok"):
        log("텔레그램 알림 전송 완료")
    else:
        log(f"텔레그램 오류: {result}")

# ── 메인 ─────────────────────────────────────────────────────
def main():
    log(f"=== 데일리 테제 자동화 시작 ({TODAY_KR}) ===")

    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY 환경변수가 없습니다.")
        sys.exit(1)

    news = fetch_news()
    if not news:
        log("⚠️ 뉴스 수집 실패 — 기본 프롬프트로 진행")
        news = ["글로벌 금융시장 동향 분석 필요"]

    analysis = call_claude(news)
    cover_svg, chart_svg = generate_svgs(analysis)
    html = build_html(analysis, cover_svg, chart_svg)
    publish(html, analysis)

    log("=== 완료 ===")

if __name__ == "__main__":
    main()
