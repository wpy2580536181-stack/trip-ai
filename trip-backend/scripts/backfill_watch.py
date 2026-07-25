"""代理自动恢复后回填剩余零命中城市的看守脚本.

背景：维基百科在中国大陆被 GFW 拦截，必须经本地代理（默认 127.0.0.1:7897）才能抓取。
用户中断代理后回填中断。本脚本轮询代理可用性，一旦维基可达即自动：
  1) fetch_wiki.py --skip-existing --limit 50 --concurrency 12  （只补缺失城市）
  2) ingest_spot_docs.py                              （本地数据入 MySQL）
  3) 写 .backfill_done 标记并退出。

用法：
    python scripts/backfill_watch.py [--max-wait 21600] [--interval 30]
"""

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_TEST = "https://zh.wikipedia.org/w/api.php?action=query&meta=siteinfo&format=json"
PROXY_CANDIDATES = ["http://127.0.0.1:7897", "http://127.0.0.1:7890"]
HEADERS = {"User-Agent": "Mozilla/5.0 (trip-backend backfill-watch)"}


def _wiki_ok(proxy: str | None, timeout: float = 12) -> bool:
    """测试维基可达性；proxy=None 表示直连。"""
    handlers = {}
    if proxy:
        # urllib 通过 env 识别代理
        handlers = None
    old_http = os.environ.get("HTTP_PROXY")
    old_https = os.environ.get("HTTPS_PROXY")
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
    else:
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
    try:
        req = urllib.request.Request(WIKI_TEST, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False
    finally:
        if old_http is None:
            os.environ.pop("HTTP_PROXY", None)
        else:
            os.environ["HTTP_PROXY"] = old_http
        if old_https is None:
            os.environ.pop("HTTPS_PROXY", None)
        else:
            os.environ["HTTPS_PROXY"] = old_https


def find_working_proxy() -> str | None | bool:
    """返回可用代理 URL；None=可直连；False=均不可达。"""
    for cand in PROXY_CANDIDATES:
        if _wiki_ok(cand):
            return cand
    if _wiki_ok(None):
        return None
    return False


def _port_listen(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        s = socket.socket()
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-wait", type=int, default=6 * 3600, help="最长等待秒数（默认 6h）")
    ap.add_argument("--interval", type=int, default=30, help="探测间隔秒数")
    args = ap.parse_args()

    log = open(os.path.join(ROOT, "data", "wiki_raw", "backfill_watch.log"), "a", encoding="utf-8")
    def logf(msg):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    logf(f"看守启动：等待代理恢复（最长 {args.max_wait}s，间隔 {args.interval}s）")
    start = time.time()
    proxy = False
    while time.time() - start < args.max_wait:
        # 快速端口探活，避免每次都发 HTTPS 请求
        if any(_port_listen("127.0.0.1", int(p.split(":")[-1])) for p in PROXY_CANDIDATES):
            proxy = find_working_proxy()
            if proxy is not False:
                break
        else:
            # 端口没起，但仍可能直连（极少见），探一次
            if _wiki_ok(None):
                proxy = None
                break
        time.sleep(args.interval)
    else:
        logf("超时：代理在等待期内未恢复，停止看守。")
        open(os.path.join(ROOT, ".backfill_done"), "w").write("timeout")
        return

    proxy_label = proxy if proxy else "直连"
    logf(f"代理可用（{proxy_label}），开始回填剩余城市...")

    env = dict(os.environ)
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
    else:
        env.pop("HTTP_PROXY", None)
        env.pop("HTTPS_PROXY", None)

    # 1) 补抓缺失城市
    try:
        subprocess.run(
            [".venv/bin/python", "scripts/fetch_wiki.py", "--skip-existing",
             "--limit", "50", "--concurrency", "12"],
            cwd=ROOT, env=env, check=True,
        )
        logf("fetch_wiki 完成")
    except subprocess.CalledProcessError as e:
        logf(f"fetch_wiki 失败：{e}")
        open(os.path.join(ROOT, ".backfill_done"), "w").write("fetch_failed")
        return

    # 2) 入库
    try:
        subprocess.run(
            [".venv/bin/python", "scripts/ingest_spot_docs.py"],
            cwd=ROOT, env=env, check=True,
        )
        logf("ingest_spot_docs 完成")
    except subprocess.CalledProcessError as e:
        logf(f"ingest 失败：{e}")
        open(os.path.join(ROOT, ".backfill_done"), "w").write("ingest_failed")
        return

    open(os.path.join(ROOT, ".backfill_done"), "w").write("done")
    logf("回填全部完成 ✅")


if __name__ == "__main__":
    main()
