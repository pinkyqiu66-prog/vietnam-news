#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vietnam News Scraper
Scrapes general and agriculture news from Vietnamese websites daily,
generates an HTML report with drone-related news highlighted.
"""

import sys
import io

# Force UTF-8 output — needed on Windows (GBK terminal), harmless on Linux
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime
from pathlib import Path
import time
import random

# ─── Translation ───────────────────────────────────────────────────────────────

try:
    from deep_translator import GoogleTranslator
    _translator = GoogleTranslator(source='vi', target='zh-CN')
    _TRANSLATE_AVAILABLE = True
except Exception:
    _TRANSLATE_AVAILABLE = False

_trans_cache = {}  # title -> zh text

def translate_title(title: str) -> str:
    """Translate a Vietnamese title to Chinese. Returns original if translation fails."""
    if not _TRANSLATE_AVAILABLE or not title:
        return title
    if title in _trans_cache:
        return _trans_cache[title]
    try:
        result = GoogleTranslator(source='vi', target='zh-CN').translate(title)
        _trans_cache[title] = result or title
        return _trans_cache[title]
    except Exception:
        _trans_cache[title] = title
        return title

# ─── Configuration ────────────────────────────────────────────────────────────

SOURCES = {
    "general": [
        {"name": "Báo Đầu Tư",   "url": "https://baodautu.vn/",             "focus": "Kinh te, dau tu, tai chinh"},
        {"name": "VnExpress",     "url": "https://vnexpress.net/",            "focus": "Thoi su, kinh te, xa hoi, quoc te"},
        {"name": "Dan Viet",      "url": "https://danviet.vn/nha-nong/",      "focus": "Nha nong, nong thon, dan sinh"},
        {"name": "Bao Chinh Phu", "url": "https://baochinhphu.vn/",          "focus": "Chinh sach chinh phu, thong bao"},
        {"name": "Tuoi Tre",      "url": "https://tuoitre.vn/",              "focus": "Thoi su, xa hoi, kinh te, giao duc"},
        {"name": "VTV Kinh Te",   "url": "https://vtv.vn/kinh-te.htm",       "focus": "Kinh te, tai chinh, thi truong"},
        {"name": "Thanh Nien",    "url": "https://thanhnien.vn/thoi-su.htm", "focus": "Thoi su, chinh tri, xa hoi, quoc te"},
    ],
    "agriculture": [
        {"name": "NN Huu Co",      "url": "https://nongnghiephuuco.vn/",                  "focus": "Nong nghiep huu co, xuat khau nong san"},
        {"name": "Nong Thon Viet", "url": "https://nongthonviet.vn/",                     "focus": "Nong thon, thi truong nong nghiep"},
        {"name": "NN Moi Truong",  "url": "https://nongnghiepmoitruong.vn/nong-nghiep/", "focus": "Nong nghiep moi truong, bien doi khi hau"},
    ],
}

# Keywords for drone-related news
DRONE_KEYWORDS = [
    "máy bay không người lái", "flycam", "drone", "uav", "thiết bị bay",
    "phun thuốc bằng drone", "drone nông nghiệp", "máy bay phun thuốc",
    "drone phun", "thiết bị không người lái", "dji", "agras",
    "phun thuốc tự động", "robot bay", "drone bán", "bán drone",
    "kinh doanh drone", "phân phối drone", "nhập khẩu drone",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

OUTPUT_DIR = Path(__file__).parent


# ─── Scraping Functions ────────────────────────────────────────────────────────

def fetch_page(url: str, retries: int = 3):
    """Fetch a page and return BeautifulSoup object."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"  [!] Attempt {attempt+1} failed for {url}: {e}")
            time.sleep(2 + random.random() * 2)
    return None


def extract_articles(soup: BeautifulSoup, source: dict) -> list:
    """Extract article titles and links from a page."""
    articles = []
    seen_titles = set()

    # Try multiple selectors to find links
    selectors = [
        "h1 a", "h2 a", "h3 a", "h4 a",
        ".title a", ".headline a", ".article-title a",
        ".news-title a", ".item-title a", ".post-title a",
        "article a", ".item a", ".entry-title a",
    ]

    for selector in selectors:
        links = soup.select(selector)
        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href", "")

            # Skip short titles, navigation items, empty
            if not title or len(title) < 5:
                continue
            if title in seen_titles:
                continue
            # Skip obvious nav/footer links
            if any(skip in title.lower() for skip in ["đăng nhập", "đăng ký", "liên hệ", "quảng cáo"]):
                continue

            # Build absolute URL
            if not isinstance(href, str):
                href = str(href) if href else ""
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(source["url"])
                full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
            else:
                continue

            seen_titles.add(title)
            articles.append({
                "title": title,
                "url": full_url,
                "source": source["name"],
                "is_drone": is_drone_related(title),
            })

        if len(articles) >= 20:
            break

    return articles[:20]  # Cap per source


def is_drone_related(text: str) -> bool:
    """Check if text contains drone-related keywords."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in DRONE_KEYWORDS)


def scrape_all() -> dict:
    """Scrape all sources and return structured data."""
    results = {
        "scraped_at": datetime.now().isoformat(),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "general": [],
        "agriculture": [],
        "drone_highlights": [],
    }

    for category, sources in SOURCES.items():
        print(f"\n[{category.upper()}]")
        for source in sources:
            url = source["url"]
            print(f"  Scraping: {url} ...", end=" ", flush=True)
            soup = fetch_page(url)
            if not soup:
                print("FAIL")
                continue
            articles = extract_articles(soup, source)
            print(f"OK ({len(articles)} articles)")

            for art in articles:
                results[category].append(art)
                if art["is_drone"]:
                    results["drone_highlights"].append({**art, "category": category})

            time.sleep(1 + random.random())  # Polite delay

    return results


# ─── HTML Generation ───────────────────────────────────────────────────────────

import html as _html_mod

def _e(s):
    return _html_mod.escape(str(s))

WEEKDAYS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def _card(art):
    dc = " drone-article" if art.get("is_drone") else ""
    db = '<span class="drone-badge">🚁 无人机</span>' if art.get("is_drone") else ""
    src_label = _e(art["source"])
    return (f'<article class="news-card{dc}"><div class="card-meta">'
            f'<span class="source-tag">{src_label}</span>{db}</div>'
            f'<h3 class="card-title"><a href="{_e(art["url"])}" target="_blank" rel="noopener">'
            f'{_e(art["title"])}</a></h3></article>')

def _mini(art, lbl, cat, delay=""):
    da = f' style="animation-delay:{delay}"' if delay else ""
    return (f'<div class="mini-card" data-cat="{cat}"{da}>'
            f'<div class="mini-meta"><span class="cat-pill pill-{cat}">{lbl}</span>'
            f'<span class="source-chip">{_e(art["source"])}</span></div>'
            f'<p class="mini-title"><a href="{_e(art["url"])}" target="_blank" rel="noopener">'
            f'{_e(art["title"])}</a></p></div>')


def generate_html(data: dict, history: list = None) -> str:
    """Single self-contained HTML file with data inlined. No server needed."""
    date_str   = data["date"]
    scraped_at = datetime.fromisoformat(data["scraped_at"]).strftime("%H:%M")
    gen_n   = len(data["general"])
    agri_n  = len(data["agriculture"])
    drone_n = len(data["drone_highlights"])

    # Build inline JSON: today's news + full history for highlights
    today_json   = generate_data_json(data)
    history_json = json.dumps(history or [], ensure_ascii=False, separators=(',', ':'))

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>越南新闻监控 {date_str}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
:root{{
  --g:#1a7a4a;--gm:#22a05f;--gl:#e8f7ee;--gbd:#b8dfc8;
  --gold:#c49010;--goldb:#fffbf0;--goldbd:#f0d080;
  --bg:#f4f8f5;--w:#fff;--bd:#d4e8db;--bd2:#c0d8ca;
  --tx:#1a2e22;--txm:#3d6b50;--txd:#7aaa8c;
  --ec:#1a6fa8;--ecb:#eef6fc;--ecd:#b0d8f0;
  --sh:0 1px 4px rgba(26,122,74,.08);--shm:0 4px 14px rgba(26,122,74,.13);
}}
body{{background:var(--bg);color:var(--tx);font-family:'Microsoft YaHei','微软雅黑','PingFang SC',sans-serif;line-height:1.7;}}
.hd{{background:var(--g);}}
.hd-top{{background:rgba(0,0,0,.18);padding:5px 32px;display:flex;align-items:center;gap:8px;}}
.hd-top span{{font-size:.65rem;letter-spacing:.06em;text-transform:uppercase;color:rgba(255,255,255,.6);}}
.dot{{width:5px;height:5px;border-radius:50%;background:#5de89a;animation:blink 2s infinite;flex-shrink:0;}}
@keyframes blink{{0%,100%{{opacity:1;}}50%{{opacity:.25;}}}}
.hd-body{{max-width:1200px;margin:0 auto;padding:20px 32px 24px;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;}}
.site-title{{font-size:clamp(1.5rem,3vw,2.3rem);font-weight:700;color:#fff;line-height:1.1;}}
.site-title b{{color:#a8f0c4;}}
.site-sub{{font-size:.7rem;color:rgba(255,255,255,.55);text-transform:uppercase;letter-spacing:.06em;margin-top:5px;}}
.hd-r{{text-align:right;}}
.hd-date{{font-size:1.4rem;font-weight:700;color:#fff;}}
.hd-time{{font-size:.63rem;color:rgba(255,255,255,.5);margin-top:2px;}}
.stats{{background:var(--w);border-bottom:1px solid var(--bd);box-shadow:var(--sh);}}
.stats-in{{max-width:1200px;margin:0 auto;padding:8px 32px;display:flex;align-items:center;flex-wrap:wrap;}}
.si{{display:flex;align-items:center;gap:7px;padding:4px 18px 4px 0;margin-right:18px;border-right:1px solid var(--bd);font-size:.75rem;color:var(--txd);}}
.si:last-child{{border-right:none;margin-right:0;margin-left:auto;}}
.sn{{font-size:1rem;font-weight:700;}} .sn.g{{color:var(--g);}} .sn.gm{{color:var(--gm);}} .sn.go{{color:var(--gold);}}
.mnav{{background:var(--w);border-bottom:2px solid var(--gbd);position:sticky;top:0;z-index:100;box-shadow:0 2px 5px rgba(26,122,74,.06);}}
.mnav-in{{max-width:1200px;margin:0 auto;padding:0 32px;display:flex;}}
.mt{{padding:12px 20px;font-size:.86rem;font-weight:600;color:var(--txd);background:none;border:none;border-bottom:3px solid transparent;margin-bottom:-2px;cursor:pointer;transition:color .15s;white-space:nowrap;}}
.mt:hover{{color:var(--g);}} .mt.on{{color:var(--g);border-bottom-color:var(--g);background:var(--gl);}} .mt.on-gold{{color:var(--gold);border-bottom-color:var(--gold);background:var(--goldb);}} .mt.on-arc{{color:#6a3da8;border-bottom-color:#6a3da8;background:#f4f0fc;}}
.tdiv{{width:1px;background:var(--bd);margin:8px 0;}}
.snav{{background:var(--w);border-bottom:1px solid var(--bd);}}
.snav-in{{max-width:1200px;margin:0 auto;padding:0 32px;display:flex;overflow-x:auto;}}
.st{{padding:9px 15px;font-size:.77rem;font-weight:500;color:var(--txd);background:none;border:none;border-bottom:2px solid transparent;margin-bottom:-1px;cursor:pointer;white-space:nowrap;}}
.st:hover{{color:var(--g);}} .st.s-drone{{color:var(--gold);border-bottom-color:var(--gold);}} .st.s-gen{{color:var(--g);border-bottom-color:var(--g);}} .st.s-agr{{color:var(--gm);border-bottom-color:var(--gm);}} .st.s-all{{color:var(--txm);border-bottom-color:var(--bd2);}}
.panel{{display:none;}} .panel.on{{display:block;}}
.mc{{max-width:1200px;margin:0 auto;padding:26px 32px 56px;}}
.sec{{display:none;}} .sec.on{{display:block;margin-bottom:36px;}}
.sec-hd{{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:10px;border-bottom:2px solid var(--gbd);}}
.sec-tag{{font-size:.6rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;padding:2px 8px;border-radius:20px;}}
.tag-g{{background:var(--gl);color:var(--g);border:1px solid var(--gbd);}} .tag-a{{background:#eaf7ef;color:var(--gm);border:1px solid #b0d8be;}} .tag-d{{background:var(--goldb);color:var(--gold);border:1px solid var(--goldbd);}}
.sec-title{{font-size:1.3rem;font-weight:700;color:var(--tx);}} .sec-cnt{{font-size:.67rem;color:var(--txd);margin-left:auto;}}
.drone-banner{{display:flex;align-items:center;gap:14px;background:var(--goldb);border:1px solid var(--goldbd);border-radius:8px;padding:14px 20px;margin-bottom:16px;}}
.drone-banner h2{{font-size:1.15rem;font-weight:700;color:var(--gold);}} .drone-banner p{{font-size:.73rem;color:#8a7040;margin-top:2px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:11px;}}
.card{{background:var(--w);border:1px solid var(--bd);border-radius:6px;padding:14px 16px;position:relative;overflow:hidden;box-shadow:var(--sh);transition:border-color .15s,transform .15s,box-shadow .15s;}}
.card::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--gbd);border-radius:6px 0 0 6px;transition:background .15s;}}
.card:hover{{border-color:var(--gm);transform:translateY(-2px);box-shadow:var(--shm);}} .card:hover::before{{background:var(--g);}}
.card.drone{{background:var(--goldb);border-color:var(--goldbd);}} .card.drone::before{{background:var(--gold)!important;}} .card.drone:hover{{border-color:var(--gold);}}
.cmeta{{display:flex;align-items:center;gap:5px;margin-bottom:6px;flex-wrap:wrap;}}
.src{{font-size:.59rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--txd);background:var(--gl);padding:2px 6px;border-radius:3px;border:1px solid var(--gbd);}}
.card.drone .src{{background:#fff8e0;border-color:var(--goldbd);color:#8a6800;}}
.dbadge{{font-size:.57rem;font-weight:700;background:var(--gold);color:#fff;padding:2px 6px;border-radius:3px;}}
.ctitle{{font-size:.85rem;line-height:1.55;}} .ctitle a{{color:var(--tx);text-decoration:none;}} .ctitle a:hover{{color:var(--g);text-decoration:underline;text-underline-offset:3px;}}
.card.drone .ctitle a:hover{{color:var(--gold);}}
.cvi{{font-size:.7rem;color:var(--txd);margin-top:3px;font-style:italic;line-height:1.4;}}
.feat{{background:var(--w);border:1px solid var(--bd);border-radius:8px;padding:18px 22px;margin-bottom:11px;position:relative;overflow:hidden;box-shadow:var(--sh);}}
.feat::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--g);border-radius:8px 0 0 8px;}}
.feat-hd{{display:flex;align-items:center;gap:6px;margin-bottom:9px;flex-wrap:wrap;}}
.fnum{{font-size:1.3rem;font-weight:700;color:var(--gbd);line-height:1;margin-right:2px;}}
.pill{{font-size:.59rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border-radius:20px;}}
.pill-g{{background:var(--ecb);color:var(--ec);border:1px solid var(--ecd);}} .pill-a{{background:var(--gl);color:var(--g);border:1px solid var(--gbd);}} .pill-d{{background:var(--goldb);color:var(--gold);border:1px solid var(--goldbd);}}
.chip{{font-size:.59rem;color:var(--txd);background:var(--gl);padding:2px 6px;border-radius:3px;border:1px solid var(--gbd);}}
.ftitle{{font-size:1rem;font-weight:700;color:var(--tx);line-height:1.42;}} .ftitle a{{color:inherit;text-decoration:none;}} .ftitle a:hover{{color:var(--g);text-decoration:underline;text-underline-offset:3px;}}
.fvi{{font-size:.72rem;color:var(--txd);margin-top:3px;font-style:italic;}}
.sgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:9px;margin-bottom:9px;}}
.mcard{{background:var(--w);border:1px solid var(--bd);border-radius:6px;padding:12px 14px;position:relative;overflow:hidden;box-shadow:var(--sh);}}
.mcard::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--gbd);border-radius:6px 0 0 6px;}}
.mcard:hover{{border-color:var(--gm);box-shadow:var(--shm);}} .mcard:hover::before{{background:var(--g);}}
.mtitle{{font-size:.83rem;font-weight:500;line-height:1.5;}} .mtitle a{{color:var(--tx);text-decoration:none;}} .mtitle a:hover{{color:var(--g);text-decoration:underline;text-underline-offset:3px;}}
.mvi{{font-size:.68rem;color:var(--txd);margin-top:3px;font-style:italic;}}
.day-hd{{display:flex;align-items:center;gap:12px;margin-bottom:18px;padding-top:8px;flex-wrap:wrap;}}
.date-badge{{flex-shrink:0;background:var(--g);border-radius:6px;padding:6px 11px;text-align:center;min-width:52px;}}
.date-day{{font-size:1.6rem;font-weight:700;color:#fff;line-height:1;}} .date-mon{{font-size:.56rem;letter-spacing:.06em;text-transform:uppercase;color:rgba(255,255,255,.65);margin-top:1px;}}
.day-info{{flex:1;min-width:120px;}} .day-wd{{font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;color:var(--txd);margin-bottom:2px;}} .day-name{{font-size:1.1rem;font-weight:700;color:var(--tx);}}
.day-div{{flex:1;height:1px;background:linear-gradient(90deg,var(--gbd),transparent);min-width:20px;}}
.day-chip{{font-size:.58rem;color:var(--txd);background:var(--w);border:1px solid var(--bd);padding:2px 8px;border-radius:20px;flex-shrink:0;}}
.sep{{margin:20px 0;display:flex;align-items:center;gap:10px;}}.drone-sub-hd{{font-size:.8rem;font-weight:600;color:var(--gold);margin:14px 0 8px;padding:6px 10px;background:var(--goldb);border-radius:4px;border-left:3px solid var(--gold);}}
.sep-line{{flex:1;height:1px;background:var(--gbd);}} .sep-dot{{width:5px;height:5px;border-radius:50%;background:var(--gbd);}}
.hl-bar{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px;}}
.hb{{padding:5px 13px;font-size:.76rem;font-weight:500;background:var(--w);border:1px solid var(--bd);border-radius:20px;cursor:pointer;color:var(--txd);transition:all .15s;}}
.hb:hover{{color:var(--g);border-color:var(--g);}} .hb.on{{background:var(--g);color:#fff;border-color:var(--g);}}
.hb-cnt{{font-size:.64rem;background:rgba(255,255,255,.2);padding:0 4px;border-radius:10px;margin-left:2px;}}
.hb:not(.on) .hb-cnt{{background:var(--gl);color:var(--g);}}
.day-block.hidden{{display:none;}}
.src-stats{{display:flex;background:var(--w);border:1px solid var(--bd);border-radius:8px;overflow:hidden;margin-bottom:24px;box-shadow:var(--sh);flex-wrap:wrap;}}
.ss{{flex:1;min-width:120px;padding:13px 16px;border-right:1px solid var(--bd);}}
.ss:last-child{{border-right:none;}}
.ss-n{{font-size:1.2rem;font-weight:700;color:var(--g);}} .ss-n.b{{color:var(--ec);}}
.ss span:last-child{{font-size:.72rem;color:var(--txd);display:block;margin-top:2px;}}
.src-sh{{display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap;}}
.src-sh h3{{font-size:1.05rem;font-weight:700;}}
.sbadge{{font-size:.58rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:20px;}}
.sbadge.g{{background:var(--ecb);color:var(--ec);border:1px solid var(--ecd);}} .sbadge.a{{background:var(--gl);color:var(--g);border:1px solid var(--gbd);}}
.sc-cnt{{margin-left:auto;font-size:.7rem;color:var(--txd);}}
.tbl{{width:100%;border-collapse:separate;border-spacing:0;background:var(--w);border:1px solid var(--bd);border-radius:8px;overflow:hidden;box-shadow:var(--sh);}}
.tbl thead tr{{background:var(--gl);}} .tbl th{{padding:9px 14px;text-align:left;font-size:.65rem;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--g);border-bottom:2px solid var(--gbd);white-space:nowrap;}}
.tbl td{{padding:10px 14px;font-size:.82rem;vertical-align:middle;}} .tbl tbody tr:not(:last-child) td{{border-bottom:1px solid var(--bd);}} .tbl tbody tr:hover{{background:var(--gl);}}
.cn{{width:40px;color:var(--txd);font-size:.7rem;font-weight:600;}} .cnm{{width:170px;font-weight:600;}} .cf{{color:var(--txm);font-size:.8rem;}} .cu{{width:240px;}}
.tpill{{display:inline-flex;align-items:center;gap:3px;font-size:.65rem;font-weight:500;padding:2px 7px;border-radius:20px;}}
.url-link{{color:var(--g);text-decoration:none;font-size:.77rem;word-break:break-all;}} .url-link:hover{{text-decoration:underline;}}
.src-tb{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:18px;flex-wrap:wrap;}}
.tb-l,.tb-r{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;}}
.btn-add{{padding:5px 13px;font-size:.78rem;font-weight:500;background:var(--g);color:#fff;border:none;border-radius:6px;cursor:pointer;}} .btn-add:hover{{background:var(--gm);}} .btn-add.a{{background:#2f8f5a;}}
.btn-save{{padding:5px 13px;font-size:.78rem;font-weight:500;background:var(--g);color:#fff;border:none;border-radius:6px;cursor:pointer;}} .btn-save:hover{{background:var(--gm);}}
.btn-rst{{padding:5px 11px;font-size:.78rem;background:var(--w);color:var(--txd);border:1px solid var(--bd);border-radius:6px;cursor:pointer;}}
.save-tip{{font-size:.73rem;color:var(--g);font-weight:500;opacity:0;transition:opacity .3s;}} .save-tip.on{{opacity:1;}}
.eb{{background:none;border:none;cursor:pointer;padding:2px 5px;border-radius:4px;font-size:.74rem;color:var(--txd);margin:0 1px;}} .eb:hover{{background:var(--gl);color:var(--g);}}
.db{{background:none;border:none;cursor:pointer;padding:2px 5px;border-radius:4px;font-size:.74rem;color:#c0392b;opacity:.4;margin:0 1px;}} .db:hover{{background:#fde8e8;opacity:1;}}
.erow td{{background:#f0faf4!important;padding:4px 8px!important;}}
.url-hidden{{display:none;}} .erow .url-hidden{{display:inline;}} .erow .url-vis{{display:none;}}
.note{{margin-top:22px;background:var(--w);border:1px solid var(--bd);border-left:4px solid var(--g);border-radius:6px;padding:13px 16px;font-size:.8rem;color:var(--txm);line-height:1.65;box-shadow:var(--sh);}}
.no-data{{color:var(--txd);font-style:italic;padding:22px;text-align:center;background:var(--w);border:1px solid var(--bd);border-radius:6px;font-size:.82rem;}}
.ft{{background:var(--g);padding:16px 32px;text-align:center;font-size:.66rem;color:rgba(255,255,255,.6);}}
.ft-srcs{{display:flex;flex-wrap:wrap;justify-content:center;gap:3px 11px;margin-top:7px;font-size:.58rem;}}
.ft-srcs a{{color:rgba(255,255,255,.42);text-decoration:none;}} .ft-srcs a:hover{{color:#fff;}}
#loading{{position:fixed;inset:0;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:999;gap:12px;}}
.spin{{width:32px;height:32px;border:3px solid var(--gbd);border-top-color:var(--g);border-radius:50%;animation:spin .65s linear infinite;}}
@keyframes spin{{to{{transform:rotate(360deg);}}}}
#loading p{{font-size:.82rem;color:var(--txd);}}
@media(max-width:768px){{
  .hd-body{{padding:14px 18px;}} .stats-in{{padding:7px 18px;}}
  .mnav-in,.snav-in{{padding:0 18px;overflow-x:auto;}}
  .mc{{padding:18px 14px 48px;}} .grid,.sgrid{{grid-template-columns:1fr;}}
  .tbl .cf{{display:none;}} .src-stats{{flex-wrap:wrap;}} .ss{{min-width:50%;}}
  .ft{{padding:12px 18px;}} .day-div{{display:none;}}
}}
</style>
</head>
<body>
<div id="loading"><div class="spin"></div><p>正在加载今日新闻…</p></div>

<header class="hd">
  <div class="hd-top"><span class="dot"></span><span>越南新闻监控 · 每日自动更新</span></div>
  <div class="hd-body">
    <div>
      <div class="site-title">越南新闻 <b>监控看板</b></div>
      <div class="site-sub">综合 · 农业 · 无人机专题 · 来源目录</div>
    </div>
    <div class="hd-r">
      <div class="hd-date" id="hd-date">{date_str}</div>
      <div class="hd-time" id="hd-time">更新于 {scraped_at}</div>
    </div>
  </div>
</header>

<div class="stats"><div class="stats-in">
  <div class="si"><span class="dot"></span><span>实时</span></div>
  <div class="si"><span class="sn g" id="sn-g">{gen_n}</span><span>综合</span></div>
  <div class="si"><span class="sn gm" id="sn-a">{agri_n}</span><span>农业</span></div>
  <div class="si"><span class="sn go" id="sn-d">{drone_n}</span><span>无人机</span></div>
  <div class="si"><span style="font-size:.67rem;color:var(--txd)">7 综合 · 3 农业 · 共10个监控源</span></div>
</div></div>

<nav class="mnav"><div class="mnav-in">
  <button class="mt on"   onclick="pg('news',this)">📰 今日新闻</button>
  <div class="tdiv"></div>
  <button class="mt"      onclick="pg('hl',this)">★ 事件概要</button>
  <div class="tdiv"></div>
  <button class="mt"      onclick="pg('arc',this)">📅 历史汇总</button>
  <div class="tdiv"></div>
  <button class="mt"      onclick="pg('src',this)">📋 来源目录</button>
</div></nav>

<div class="panel on" id="p-news">
  <nav class="snav"><div class="snav-in">
    <button class="st s-drone" onclick="sub('drone',this)">🚁 无人机</button>
    <button class="st"         onclick="sub('gen',this)">综合新闻</button>
    <button class="st"         onclick="sub('agr',this)">农业新闻</button>
    <button class="st"         onclick="sub('all',this)">全部</button>
  </div></nav>
  <div class="mc">
    <div class="sec on" id="s-drone">
      <div class="drone-banner"><span style="font-size:1.7rem">🚁</span>
        <div><h2>无人机 &amp; UAV 专题</h2><p>含无人机、植保机、UAV、DJI 等关键词报道</p></div>
      </div>
      <div class="grid" id="g-drone"></div>
    </div>
    <div class="sec" id="s-gen">
      <div class="sec-hd"><span class="sec-tag tag-g">综合</span><h2 class="sec-title">综合新闻</h2><span class="sec-cnt" id="cnt-gen"></span></div>
      <div class="grid" id="g-gen"></div>
    </div>
    <div class="sec" id="s-agr">
      <div class="sec-hd"><span class="sec-tag tag-a">农业</span><h2 class="sec-title">农业新闻</h2><span class="sec-cnt" id="cnt-agr"></span></div>
      <div class="grid" id="g-agr"></div>
    </div>
  </div>
</div>

<div class="panel" id="p-hl">
  <div class="mc">
    <div class="hl-bar" id="hl-bar"></div>
    <div id="hl-content"></div>
  </div>
</div>

<div class="panel" id="p-arc">
  <div class="mc">
    <div class="hl-bar" id="arc-bar"></div>
    <div id="arc-content"></div>
  </div>
</div>

<div class="panel" id="p-src">
  <div class="mc">
    <div class="src-stats">
      <div class="ss"><span class="ss-n" id="ss-tot">10</span><span>监控来源总数</span></div>
      <div class="ss"><span class="ss-n b" id="ss-gen">7</span><span>综合类</span></div>
      <div class="ss"><span class="ss-n" id="ss-agr">3</span><span>农业类</span></div>
      <div class="ss"><span style="font-size:.7rem;color:var(--txd)">每日 08:30 自动抓取</span></div>
    </div>
    <div class="src-tb">
      <div class="tb-l">
        <button class="btn-add"   onclick="addRow('g')">＋ 新增综合</button>
        <button class="btn-add a" onclick="addRow('a')">＋ 新增农业</button>
      </div>
      <div class="tb-r">
        <span class="save-tip" id="stip"></span>
        <button class="btn-save" onclick="saveSrc()">💾 保存</button>
        <button class="btn-rst"  onclick="resetSrc()">↺ 恢复默认</button>
      </div>
    </div>
    <div style="margin-bottom:28px">
      <div class="src-sh"><span style="font-size:1.2rem">🗞️</span><h3>综合类新闻</h3><span class="sbadge g">综合</span><span class="sc-cnt" id="sc-g">7 个来源</span></div>
      <table class="tbl"><thead><tr><th>#</th><th>名称</th><th>类型</th><th>报道重点</th><th>网址</th><th style="width:68px;text-align:center">操作</th></tr></thead><tbody id="tb-g"></tbody></table>
    </div>
    <div>
      <div class="src-sh"><span style="font-size:1.2rem">🌿</span><h3>农业类新闻</h3><span class="sbadge a">农业</span><span class="sc-cnt" id="sc-a">3 个来源</span></div>
      <table class="tbl"><thead><tr><th>#</th><th>名称</th><th>类型</th><th>报道重点</th><th>网址</th><th style="width:68px;text-align:center">操作</th></tr></thead><tbody id="tb-a"></tbody></table>
    </div>
    <div class="note"><strong>说明：</strong>编辑保存在浏览器本地（localStorage），刷新后依然保留。如需同步到抓取程序，请修改 <code style="background:#f0f5f2;padding:1px 4px;border-radius:3px;color:var(--g)">scraper.py</code> 的 SOURCES 配置。</div>
  </div>
</div>

<footer class="ft">
  <div>越南新闻监控系统 · 每日 08:30 自动更新</div>
  <div class="ft-srcs" id="ft-srcs"></div>
</footer>

<script>
function esc(s){{const d=document.createElement('div');d.textContent=s;return d.innerHTML;}}

(function(){{
  const d = __TODAY__;
  const HIST = __HIST__;
  document.getElementById('loading').style.display='none';
  document.getElementById('hd-date').textContent=d.date;
  document.getElementById('hd-time').textContent='更新于 '+d.updated;
  document.getElementById('sn-g').textContent=d.general.length;
  document.getElementById('sn-a').textContent=d.agri.length;
  document.getElementById('sn-d').textContent=d.drone.length;
  renderNews(d); renderHL(); renderArc(); renderFt(d);
}})();

function card(a){{
  const dc=a.d?' drone':'',db=a.d?'<span class="dbadge">🚁 无人机</span>':'';
  return `<div class="card${{dc}}"><div class="cmeta"><span class="src">${{esc(a.s)}}</span>${{db}}</div>
    <div class="ctitle"><a href="${{esc(a.u)}}" target="_blank">${{esc(a.t)}}</a></div>
    ${{a.tv!==a.t?`<div class="cvi">${{esc(a.tv)}}</div>`:''}}</div>`;
}}

function renderNews(d){{
  document.getElementById('g-gen').innerHTML=d.general.map(card).join('')||'<p class="no-data">今日暂无综合新闻</p>';
  document.getElementById('g-agr').innerHTML=d.agri.map(card).join('')||'<p class="no-data">今日暂无农业新闻</p>';
  document.getElementById('g-drone').innerHTML=d.drone.map(card).join('')||'<p class="no-data">今日暂无无人机相关报道（关键词：drone/UAV/飞行器/植保机/DJI）</p>';
  document.getElementById('cnt-gen').textContent=d.general.length+' 篇';
  document.getElementById('cnt-agr').textContent=d.agri.length+' 篇';
}}

function oneDayBlock(d, idx, prefix){{
  const all=[...d.general,...d.agri];
  const dp=d.date.split('/');
  let h=`<div class="day-block" id="${{prefix}}-${{idx}}" data-date="${{d.date}}"><div class="day-hd">
    <div class="date-badge"><div class="date-day">${{dp[0]}}</div><div class="date-mon">${{dp[1]}}月</div></div>
    <div class="day-info"><div class="day-wd">${{d.weekday}} · ${{dp[2]}}</div><div class="day-name">${{dp[0]}}日 大事件汇总</div></div>
    <div class="day-div"></div><div class="day-chip">${{all.length}} 条新闻</div></div>`;
  if(all.length>0){{
    const f=all[0],fp=d.general.length>0&&d.general[0]===f?'pill-g':'pill-a',fl=fp==='pill-g'?'综合':'农业';
    h+=`<div class="feat" data-cat="${{fl==='综合'?'econ':'agri'}}">
      <div class="feat-hd"><span class="fnum">01</span><span class="pill ${{fp}}">${{fl}}</span><span class="chip">${{esc(f.s)}}</span></div>
      <div class="ftitle"><a href="${{esc(f.u)}}" target="_blank">${{esc(f.t)}}</a></div>
      ${{f.tv&&f.tv!==f.t?`<div class="fvi">${{esc(f.tv)}}</div>`:''}}</div>`;
    const rest=all.slice(1,7);
    if(rest.length){{
      h+='<div class="sgrid">';
      rest.forEach((a,ri)=>{{
        const cat=ri<d.general.length-1?'econ':'agri',lbl=cat==='econ'?'综合':'农业';
        h+=`<div class="mcard" data-cat="${{cat}}">
          <div class="cmeta"><span class="pill pill-${{cat==='econ'?'g':'a'}}">${{lbl}}</span><span class="chip">${{esc(a.s)}}</span></div>
          <div class="mtitle"><a href="${{esc(a.u)}}" target="_blank">${{esc(a.t)}}</a></div>
          ${{a.tv&&a.tv!==a.t?`<div class="mvi">${{esc(a.tv)}}</div>`:''}}</div>`;
      }});
      h+='</div>';
    }}
  }}
  if(d.drone.length){{
    h+=`<div class="drone-sub-hd">🚁 无人机相关报道（${{d.drone.length}} 条）</div><div class="sgrid">`;
    d.drone.forEach(a=>{{h+=`<div class="mcard" data-cat="drone">
      <div class="cmeta"><span class="pill pill-d">无人机</span><span class="chip">${{esc(a.s)}}</span></div>
      <div class="mtitle"><a href="${{esc(a.u)}}" target="_blank">${{esc(a.t)}}</a></div>
      ${{a.tv&&a.tv!==a.t?`<div class="mvi">${{esc(a.tv)}}</div>`:''}}</div>`;
    }});
    h+='</div>';
  }}
  h+='</div>';
  return h;
}}

// ── 事件概要：只显示当天 ──
function renderHL(){{
  const d=HIST[0];
  if(!d){{ document.getElementById('hl-content').innerHTML='<p class="no-data">暂无今日数据</p>'; return; }}
  const all=[...d.general,...d.agri];
  document.getElementById('hl-bar').innerHTML=
    [['all','全部',all.length],['drone','🚁 无人机',d.drone.length],['econ','综合',d.general.length],['agri','农业',d.agri.length]]
    .map(([k,l,n])=>`<button class="hb${{k==='all'?' on':''}}" onclick="hlFilter('hl-content','${{k}}',this)">${{l}}<span class="hb-cnt">${{n}}</span></button>`).join('');
  document.getElementById('hl-content').innerHTML=oneDayBlock(d,0,'hl');
}}

// ── 历史汇总：所有天，从新到旧 ──
function renderArc(){{
  const totalG=HIST.reduce((s,d)=>s+d.general.length,0);
  const totalA=HIST.reduce((s,d)=>s+d.agri.length,0);
  const totalD=HIST.reduce((s,d)=>s+d.drone.length,0);
  const totalAll=totalG+totalA;
  document.getElementById('arc-bar').innerHTML=
    [['all','全部',totalAll],['drone','🚁 无人机',totalD],['econ','综合',totalG],['agri','农业',totalA]]
    .map(([k,l,n])=>`<button class="hb${{k==='all'?' on':''}}" onclick="hlFilter('arc-content','${{k}}',this)">${{l}}<span class="hb-cnt">${{n}}</span></button>`).join('');
  let h='';
  HIST.forEach((d,i)=>{{
    h+=oneDayBlock(d,i,'arc');
    if(i<HIST.length-1) h+='<div class="sep"><div class="sep-line"></div><div class="sep-dot"></div><div class="sep-line"></div></div>';
  }});
  document.getElementById('arc-content').innerHTML=h||'<p class="no-data">暂无历史数据</p>';
}}

function renderFt(d){{
  const srcs=[...new Set([...d.general,...d.agri,...d.drone].map(a=>a.s))];
  document.getElementById('ft-srcs').innerHTML=srcs.map(s=>`<span><a href="#">${{esc(s)}}</a></span>`).join('');
}}

function pg(name,btn){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  document.getElementById('p-'+name).classList.add('on');
  document.querySelectorAll('.mt').forEach(b=>b.classList.remove('on','on-gold','on-arc'));
  if(name==='hl') btn.classList.add('on-gold');
  else if(name==='arc') btn.classList.add('on-arc');
  else btn.classList.add('on');
  window.scrollTo({{top:0,behavior:'smooth'}});
}}
function sub(name,btn){{
  document.querySelectorAll('#p-news .sec').forEach(s=>s.classList.remove('on'));
  document.querySelectorAll('.st').forEach(b=>b.className='st');
  if(name==='all'){{document.querySelectorAll('#p-news .sec').forEach(s=>s.classList.add('on'));btn.className='st s-all';}}
  else{{document.getElementById('s-'+name).classList.add('on');btn.className='st s-'+name;}}
  window.scrollTo({{top:0,behavior:'smooth'}});
}}
function hlFilter(containerId,cat,btn){{
  const bar=btn.closest('.hl-bar');
  bar.querySelectorAll('.hb').forEach(b=>b.classList.remove('on'));btn.classList.add('on');
  const ct=document.getElementById(containerId);
  const cards=ct.querySelectorAll('[data-cat]'),blocks=ct.querySelectorAll('.day-block');
  if(cat==='all'){{blocks.forEach(b=>b.classList.remove('hidden'));cards.forEach(c=>c.style.display='');}}
  else{{
    cards.forEach(c=>c.style.display=c.dataset.cat===cat?'':'none');
    blocks.forEach(b=>{{const v=[...b.querySelectorAll('[data-cat]')].some(c=>c.dataset.cat===cat);b.classList.toggle('hidden',!v);}});
  }}
}}

const DEF={{
  g:[
    {{n:"Báo Đầu Tư",u:"https://baodautu.vn/",f:"经济、投资、金融、政策"}},
    {{n:"VnExpress",u:"https://vnexpress.net/",f:"时事、经济、社会、国际"}},
    {{n:"Dân Việt",u:"https://danviet.vn/nha-nong/",f:"农民、农村、民生、社会"}},
    {{n:"Báo Chính Phủ",u:"https://baochinhphu.vn/",f:"政府政策、官方公告、法规"}},
    {{n:"Tuổi Trẻ",u:"https://tuoitre.vn/",f:"时事、社会、经济、教育"}},
    {{n:"VTV Kinh Tế",u:"https://vtv.vn/kinh-te.htm",f:"经济、财经、市场动态"}},
    {{n:"Thanh Niên",u:"https://thanhnien.vn/thoi-su.htm",f:"时事、政治、社会、国际"}},
  ],
  a:[
    {{n:"Nông Nghiệp Hữu Cơ",u:"https://nongnghiephuuco.vn/",f:"有机农业、种植技术、出口农产品"}},
    {{n:"Nông Thôn Việt",u:"https://nongthonviet.vn/",f:"农村发展、农业市场、粮食价格"}},
    {{n:"Nông Nghiệp Môi Trường",u:"https://nongnghiepmoitruong.vn/nong-nghiep/",f:"农业环保、生态种植、气候影响"}},
  ]
}};
const SK='vn_src_v1';
function loadSrc(){{try{{const r=localStorage.getItem(SK);if(r){{const p=JSON.parse(r);if((p.g&&p.g.length>0)||(p.a&&p.a.length>0))return p;}}return JSON.parse(JSON.stringify(DEF));}}catch(e){{return JSON.parse(JSON.stringify(DEF));}}}}
function saveSrc(){{
  const d={{g:collectRows('g'),a:collectRows('a')}};
  localStorage.setItem(SK,JSON.stringify(d));updateSS(d);
  const t=document.getElementById('stip');t.textContent='✓ 已保存';t.classList.add('on');setTimeout(()=>t.classList.remove('on'),2500);
}}
function resetSrc(){{if(!confirm('确定恢复默认？'))return;localStorage.removeItem(SK);renderSrc(JSON.parse(JSON.stringify(DEF)));}}
function collectRows(cat){{return[...document.querySelectorAll('#tb-'+cat+' tr')].map(tr=>{{return{{n:tr.querySelector('[data-f=n]').textContent.trim(),u:tr.querySelector('[data-f=u]').textContent.trim(),f:tr.querySelector('[data-f=f]').textContent.trim()}};}}).filter(r=>r.n&&r.u);}}
function updateSS(d){{document.getElementById('ss-tot').textContent=d.g.length+d.a.length;document.getElementById('ss-gen').textContent=d.g.length;document.getElementById('ss-agr').textContent=d.a.length;document.getElementById('sc-g').textContent=d.g.length+' 个来源';document.getElementById('sc-a').textContent=d.a.length+' 个来源';}}
function makeRow(item,i,cat){{
  const pill=cat==='g'?'<span class="tpill tag-g">综合</span>':'<span class="tpill tag-a">农业</span>';
  const ud=item.u.replace(/^https?:\\/\\//,'').replace(/\\/$/,'');
  const tr=document.createElement('tr');
  tr.innerHTML=`<td class="cn">${{String(i).padStart(2,'0')}}</td>
    <td class="cnm" data-f="n" contenteditable="false">${{esc(item.n)}}</td>
    <td>${{pill}}</td><td class="cf" data-f="f" contenteditable="false">${{esc(item.f)}}</td>
    <td class="cu"><span data-f="u" contenteditable="false" class="url-hidden">${{esc(item.u)}}</span><a href="${{esc(item.u)}}" target="_blank" class="url-link url-vis">↗ ${{esc(ud)}}</a></td>
    <td style="text-align:center;white-space:nowrap"><button class="eb" onclick="toggleEdit(this)">✏️</button><button class="db" onclick="delRow(this)">🗑</button></td>`;
  return tr;
}}
function toggleEdit(btn){{
  const tr=btn.closest('tr'),ed=tr.classList.contains('erow');
  if(ed){{
    tr.querySelectorAll('[contenteditable]').forEach(el=>{{el.contentEditable='false';el.style.cssText='';}});
    const uv=tr.querySelector('[data-f=u]').textContent.trim(),al=tr.querySelector('.url-vis');
    al.href=uv;al.textContent='↗ '+uv.replace(/^https?:\\/\\//,'').replace(/\\/$/,'');
    tr.classList.remove('erow');btn.textContent='✏️';renum(tr.closest('tbody'));
  }}else{{
    tr.classList.add('erow');
    tr.querySelectorAll('[data-f]').forEach(el=>{{el.contentEditable='true';el.style.border='1px solid var(--gbd)';el.style.padding='2px 6px';el.style.borderRadius='4px';}});
    tr.querySelector('[data-f=n]').focus();btn.textContent='✔';
  }}
}}
function delRow(btn){{if(!confirm('确定删除？'))return;const tr=btn.closest('tr'),tb=tr.closest('tbody');tr.style.transition='opacity .2s';tr.style.opacity='0';setTimeout(()=>{{tr.remove();renum(tb);}},220);}}
function renum(tb){{[...tb.querySelectorAll('tr')].forEach((tr,i)=>{{const n=tr.querySelector('.cn');if(n)n.textContent=String(i+1).padStart(2,'0');}});}}
function addRow(cat){{const tb=document.getElementById('tb-'+cat),tr=makeRow({{n:'新来源名称',u:'https://',f:'报道重点'}},tb.querySelectorAll('tr').length+1,cat);tb.appendChild(tr);toggleEdit(tr.querySelector('.eb'));tr.scrollIntoView({{behavior:'smooth',block:'center'}});}}
function renderSrc(d){{['g','a'].forEach(cat=>{{const tb=document.getElementById('tb-'+cat);tb.innerHTML='';(d[cat]||[]).forEach((it,i)=>tb.appendChild(makeRow(it,i+1,cat)));}}); updateSS(d);}}
renderSrc(loadSrc());
</script>
</body>
</html>"""
    return html.replace("__TODAY__", today_json).replace("__HIST__", history_json)


def generate_data_json(data: dict) -> str:
    """Generate a compact data.json consumed by the static index.html template.
    Only keeps the articles needed for rendering (highlights use top 20 general,
    top 8 agri, all drone). Full news lists are truncated to top 20 per category.
    """
    date_obj = datetime.fromisoformat(data.get("date_iso", datetime.now().strftime("%Y-%m-%d")))
    weekday  = WEEKDAYS_ZH[date_obj.weekday()]

    def art_obj(a):
        return {
            "t":  a.get("title_zh") or a["title"],   # Chinese title (or original)
            "tv": a["title"],                          # Vietnamese original
            "u":  a["url"],
            "s":  a["source"],
            "d":  1 if a.get("is_drone") else 0,
        }

    out = {
        "date":      data["date"],
        "weekday":   weekday,
        "updated":   datetime.fromisoformat(data["scraped_at"]).strftime("%H:%M"),
        "general":   [art_obj(a) for a in data["general"][:20]],
        "agri":      [art_obj(a) for a in data["agriculture"][:20]],
        "drone":     [art_obj(a) for a in data["drone_highlights"][:10]],
    }
    return json.dumps(out, ensure_ascii=False, separators=(',', ':'))


def load_all_history(output_dir: Path) -> list:
    """Load all news_YYYYMMDD.json files, sorted newest first.
    Returns list of compact day-dicts ready for the highlights timeline."""
    files = sorted(output_dir.glob("news_2*.json"), reverse=True)
    days = []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
            date_iso = d.get("date_iso", "")
            if not date_iso:
                # infer from filename news_YYYYMMDD.json
                stem = fp.stem  # news_20260728
                date_iso = f"{stem[5:9]}-{stem[9:11]}-{stem[11:13]}"
            date_obj = datetime.fromisoformat(date_iso)
            weekday  = WEEKDAYS_ZH[date_obj.weekday()]

            def ao(a):
                return {
                    "t": a.get("title_zh") or a.get("title",""),
                    "tv": a.get("title",""),
                    "u": a.get("url",""),
                    "s": a.get("source",""),
                    "d": 1 if a.get("is_drone") else 0,
                }

            days.append({
                "date":    d.get("date", date_obj.strftime("%d/%m/%Y")),
                "date_iso": date_iso,
                "weekday": weekday,
                "general": [ao(a) for a in d.get("general", [])[:20]],
                "agri":    [ao(a) for a in d.get("agriculture", [])[:20]],
                "drone":   [ao(a) for a in d.get("drone_highlights", [])[:10]],
            })
        except Exception as e:
            print(f"  [warn] Could not load {fp.name}: {e}")
    return days

def translate_all(data: dict):
    """Batch-translate ALL article titles to Chinese using separator trick."""
    if not _TRANSLATE_AVAILABLE:
        print("  Translation not available, skipping.")
        return

    all_arts = data["general"] + data["agriculture"] + data["drone_highlights"]
    # deduplicate by title
    seen, unique = set(), []
    for a in all_arts:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    total = len(unique)
    print(f"  Translating {total} unique titles in batches...", flush=True)

    SEP = "\n###\n"  # newline-based separator, more reliable
    BATCH = 10       # smaller batch = less chance of separator loss

    for i in range(0, total, BATCH):
        batch = unique[i:i+BATCH]
        titles = [a["title"] for a in batch]
        combined = SEP.join(titles)
        try:
            translated = GoogleTranslator(source='vi', target='zh-CN').translate(combined)
            parts = translated.split(SEP)
            if len(parts) == len(batch):
                for a, zh in zip(batch, parts):
                    _trans_cache[a["title"]] = zh.strip() or a["title"]
            else:
                # fallback: assign what we got, fill rest with originals
                for j, a in enumerate(batch):
                    _trans_cache[a["title"]] = parts[j].strip() if j < len(parts) else a["title"]
        except Exception as e:
            print(f"  [warn] batch {i//BATCH+1} failed: {e}")
            for a in batch:
                _trans_cache[a["title"]] = a["title"]
        time.sleep(0.3)
        if (i // BATCH + 1) % 3 == 0:
            print(f"    {min(i+BATCH, total)}/{total}...", flush=True)

    # write back title_zh to all articles
    for a in all_arts:
        a["title_zh"] = _trans_cache.get(a["title"], a["title"])

    print(f"  Translation done ({total} titles).")


def main():
    now = datetime.now()
    print(f"\n{'='*55}")
    print(f"  Vietnam News Daily Scraper  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    data = scrape_all()
    data["date_iso"] = now.strftime("%Y-%m-%d")

    # Translate ALL articles to Chinese
    translate_all(data)

    # Save full JSON archive (with translations)
    json_path = OUTPUT_DIR / f"news_{now.strftime('%Y%m%d')}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[JSON]  {json_path}")

    # Generate full self-contained HTML (with all history)
    history = load_all_history(OUTPUT_DIR)
    print(f"  Loaded {len(history)} days of history for highlights timeline.")
    page = generate_html(data, history)
    dated_path = OUTPUT_DIR / f"news_{now.strftime('%Y%m%d')}.html"
    with open(dated_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[HTML]  {dated_path}")

    # Also overwrite index.html (local)
    index_path = OUTPUT_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[INDEX] {index_path}")

    # Generate compact data.json for GitHub Pages static template
    data_json = generate_data_json(data)
    data_path = OUTPUT_DIR / "data.json"
    with open(data_path, "w", encoding="utf-8") as f:
        f.write(data_json)
    print(f"[DATA]  {data_path}  ({len(data_json)//1024}KB)")

    print(f"\n  General  : {len(data['general'])} articles")
    print(f"  Agri     : {len(data['agriculture'])} articles")
    print(f"  Drone    : {len(data['drone_highlights'])} articles")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()

