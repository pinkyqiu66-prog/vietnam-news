#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam News Scheduler
后台常驻，每天定时运行爬虫。
Usage:
  python scheduler.py           # 常驻模式（启动后立即抓一次，之后每天 RUN_TIME 自动运行）
  python scheduler.py --now     # 只运行一次立即退出
  python scheduler.py --no-init # 常驻模式但启动时不立即抓取
"""

import sys
import io
import subprocess
import time
import logging
from datetime import datetime, date
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SCRIPT   = BASE_DIR / "scraper.py"
LOG_FILE = BASE_DIR / "scheduler.log"

# ── 配置 ──────────────────────────────────────────────────────────────────────
RUN_TIME = "08:30"   # 每天运行时间（本地时间，24小时制）

# ── 日志 ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def run_scraper():
    log.info("Starting scrape...")
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # 把 scraper 的输出写进日志
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                log.info("  [scraper] %s", line)
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                log.warning("  [scraper:err] %s", line)

        if result.returncode == 0:
            log.info("Scrape completed successfully.")
        else:
            log.error("Scrape failed with exit code %d.", result.returncode)
    except Exception as e:
        log.exception("Unexpected error while running scraper: %s", e)


def main():
    if "--now" in sys.argv:
        run_scraper()
        return

    no_init = "--no-init" in sys.argv
    log.info("Vietnam News Scheduler started. Daily run time: %s", RUN_TIME)
    log.info("Log file: %s", LOG_FILE)
    log.info("Press Ctrl+C to stop.")

    last_run_date = None

    # 启动时立即运行一次（除非传了 --no-init）
    if not no_init:
        log.info("Running initial scrape on startup...")
        run_scraper()
        last_run_date = date.today()

    while True:
        try:
            now = datetime.now()
            today = now.date()
            current_time = now.strftime("%H:%M")

            # 到达运行时间且今天还没运行过
            if current_time == RUN_TIME and last_run_date != today:
                run_scraper()
                last_run_date = today
                time.sleep(61)   # 跳过同一分钟内的重复触发
            else:
                time.sleep(30)   # 每 30 秒检查一次

        except KeyboardInterrupt:
            log.info("Scheduler stopped by user.")
            break
        except Exception as e:
            log.exception("Scheduler loop error: %s", e)
            time.sleep(60)


if __name__ == "__main__":
    main()
