#!/usr/bin/env python3
"""
科技股智能研究平台 — 定时爬虫
数据源：东方财富实时行情 API
输出：data/stocks.json, data/indices.json
"""

import json
import os
import sys
import time
from datetime import datetime

import requests

# ── 配置 ──────────────────────────────────────────────
EM_STOCK_API = "http://push2.eastmoney.com/api/qt/ulist.np/get"
EM_INDEX_API = "http://push2.eastmoney.com/api/qt/stock/get"
HEADERS = {"Referer": "https://quote.eastmoney.com/"}
TIMEOUT = 15
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# ── 股票标的池 — 东方财富 secid 格式：市场.代码（1=沪, 0=深）────
STOCK_POOL = [
    {"secid": "1.603501", "code": "603501", "name": "豪威集团",  "rating": "strong", "ratingLabel": "强烈关注", "target": 180,  "conf": 88, "catalyst": "Q2财报毛利率兑现"},
    {"secid": "0.002241", "code": "002241", "name": "歌尔股份",  "rating": "hold",   "ratingLabel": "中性持有", "target": 32,   "conf": 55, "catalyst": "苹果新品发布"},
    {"secid": "0.300308", "code": "300308", "name": "中际旭创",  "rating": "buy",    "ratingLabel": "积极配置", "target": 1400, "conf": 82, "catalyst": "800G/1.6T量产进度"},
    {"secid": "1.688012", "code": "688012", "name": "中微公司",  "rating": "strong", "ratingLabel": "强烈关注", "target": 580,  "conf": 85, "catalyst": "刻蚀机新客户导入"},
    {"secid": "0.300124", "code": "300124", "name": "汇川技术",  "rating": "buy",    "ratingLabel": "积极配置", "target": 95,   "conf": 76, "catalyst": "机器人订单公告"},
    {"secid": "1.688223", "code": "688223", "name": "晶科能源",  "rating": "watch",  "ratingLabel": "审慎观望", "target": 8.5,  "conf": 48, "catalyst": "Q3组件出货数据"},
    {"secid": "1.603160", "code": "603160", "name": "汇顶科技",  "rating": "buy",    "ratingLabel": "积极配置", "target": 82,   "conf": 78, "catalyst": "新一代指纹芯片量产"},
    {"secid": "0.002475", "code": "002475", "name": "立讯精密",  "rating": "hold",   "ratingLabel": "中性持有", "target": 85,   "conf": 60, "catalyst": "苹果链复苏节奏"},
]

# ── 指数配置 ──────────────────────────────────────────
INDEX_POOL = [
    {"secid": "1.000001", "name": "上证指数",   "divisor": 100},
    {"secid": "0.399001", "name": "深证成指",   "divisor": 100},
    {"secid": "1.000688", "name": "科创50",     "divisor": 100},
    {"secid": "0.399006", "name": "创业板指",   "divisor": 100},
    {"secid": "1.000990", "name": "半导体指数", "divisor": 100},
]


def fetch_with_retry(url, params, max_retries=3):
    """带重试的 HTTP 请求"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            data = resp.json()
            if data.get("rc") == 0 and data.get("data"):
                return data
            print(f"[WARN] fetch attempt {attempt+1}: rc={data.get('rc')}", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] fetch attempt {attempt+1}: {e}", file=sys.stderr)
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))
    print(f"[FATAL] fetch: all {max_retries} attempts failed", file=sys.stderr)
    return None


def scrape_stocks():
    """批量抓取股票行情 — 东方财富 ulist API"""
    secids = ",".join(s["secid"] for s in STOCK_POOL)
    data = fetch_with_retry(EM_STOCK_API, {
        "fltt": "2",
        "fields": "f2,f3,f12,f14",
        "secids": secids,
    })

    if not data:
        print("[SKIP] stocks: no data", file=sys.stderr)
        return

    # 按 code 建索引
    stock_map = {item["f12"]: item for item in data["data"]["diff"]}

    results = []
    for s in STOCK_POOL:
        item = stock_map.get(s["code"])
        if not item:
            print(f"[WARN] stock {s['code']} not found in response", file=sys.stderr)
            continue
        # 东方财富 f2 价格单位是「分」，需除以 100
        price = item["f2"] / 100 if item["f2"] else 0
        chg = item["f3"] if item["f3"] else 0
        results.append({
            "code": s["code"],
            "name": s["name"],
            "price": round(price, 2),
            "chg": round(chg, 2),
            "rating": s["rating"],
            "ratingLabel": s["ratingLabel"],
            "target": s["target"],
            "upside": round((s["target"] - price) / price * 100, 1) if price else 0,
            "conf": s["conf"],
            "catalyst": s["catalyst"],
        })

    path = os.path.join(DATA_DIR, "stocks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stocks": results},
                  f, ensure_ascii=False, indent=2)
    print(f"[OK] stocks.json — {len(results)} stocks")


def scrape_indices():
    """逐个抓取指数行情"""
    results = []
    for idx in INDEX_POOL:
        data = fetch_with_retry(EM_INDEX_API, {
            "secid": idx["secid"],
            "fields": "f43,f57,f58,f170",
        })
        if not data:
            continue
        d = data["data"]
        raw_val = d.get("f43", 0)
        if not raw_val:
            continue
        val = raw_val / idx["divisor"] if idx["divisor"] else raw_val
        chg = d.get("f170", 0) / 100 if d.get("f170") else 0

        results.append({
            "name": idx["name"],
            "val": round(val, 2),
            "chg": round(chg, 2),
            "dir": "up" if chg >= 0 else "down",
        })

    path = os.path.join(DATA_DIR, "indices.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "indices": results},
                  f, ensure_ascii=False, indent=2)
    print(f"[OK] indices.json — {len(results)} indices")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"[{datetime.now()}] Starting scrape (EastMoney API)...")
    scrape_indices()
    scrape_stocks()
    print(f"[{datetime.now()}] Done.")


if __name__ == "__main__":
    main()
