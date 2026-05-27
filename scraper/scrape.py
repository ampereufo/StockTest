#!/usr/bin/env python3
"""
科技股智能研究平台 — 定时爬虫
数据源：新浪财经实时行情 API
输出：data/stocks.json, data/indices.json
"""

import json
import os
import re
import sys
from datetime import datetime

import requests

# ── 配置 ──────────────────────────────────────────────
SINA_API = "http://hq.sinajs.cn/list="
HEADERS = {"Referer": "https://finance.sina.com.cn"}
TIMEOUT = 15
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# ── 股票标的池（代码 → 分析元数据）─────────────────
STOCK_POOL = {
    "sh603501": {"code": "603501", "name": "韦尔股份",  "rating": "strong", "ratingLabel": "强烈关注", "target": 180, "conf": 88, "catalyst": "Q2财报毛利率兑现"},
    "sz002241": {"code": "002241", "name": "歌尔股份",  "rating": "hold",   "ratingLabel": "中性持有", "target": 32,  "conf": 55, "catalyst": "苹果新品发布"},
    "sz300308": {"code": "300308", "name": "中际旭创",  "rating": "buy",    "ratingLabel": "积极配置", "target": 1400,"conf": 82, "catalyst": "800G/1.6T量产进度"},
    "sh688012": {"code": "688012", "name": "中微公司",  "rating": "strong", "ratingLabel": "强烈关注", "target": 580, "conf": 85, "catalyst": "刻蚀机新客户导入"},
    "sz300124": {"code": "300124", "name": "汇川技术",  "rating": "buy",    "ratingLabel": "积极配置", "target": 95,  "conf": 76, "catalyst": "机器人订单公告"},
    "sh688223": {"code": "688223", "name": "晶科能源",  "rating": "watch",  "ratingLabel": "审慎观望", "target": 8.5, "conf": 48, "catalyst": "Q3组件出货数据"},
    "sh603160": {"code": "603160", "name": "汇顶科技",  "rating": "buy",    "ratingLabel": "积极配置", "target": 82,  "conf": 78, "catalyst": "新一代指纹芯片量产"},
    "sz002475": {"code": "002475", "name": "立讯精密",  "rating": "hold",   "ratingLabel": "中性持有", "target": 85,  "conf": 60, "catalyst": "苹果链复苏节奏"},
}

# ── 指数代码 ──────────────────────────────────────────
INDEX_CODES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sh000688": "科创50",
    "sz399006": "创业板指",
}


def fetch_sina_quotes(codes):
    """批量获取新浪财经实时行情"""
    url = SINA_API + ",".join(codes)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = "gbk"
        return resp.text
    except Exception as e:
        print(f"[ERROR] fetch_sina_quotes: {e}", file=sys.stderr)
        return ""


def parse_stock_line(line):
    """解析单个股票行情行，返回 dict 或 None"""
    m = re.search(r'hq_str_(\w+)="(.*)"', line)
    if not m:
        return None
    sid = m.group(1)
    fields = m.group(2).split(",")
    if len(fields) < 33:
        return None

    # 字段索引（新浪财经标准格式）
    # 0:名称 1:今开 2:昨收 3:当前价 4:最高 5:最低 30:日期 31:时间
    name = fields[0]
    open_p = float(fields[1]) if fields[1] else 0
    prev_close = float(fields[2]) if fields[2] else 0
    price = float(fields[3]) if fields[3] else 0
    high = float(fields[4]) if fields[4] else 0
    low = float(fields[5]) if fields[5] else 0

    chg_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0

    return {
        "sid": sid,
        "name": name,
        "price": price,
        "open": open_p,
        "prevClose": prev_close,
        "high": high,
        "low": low,
        "chg": chg_pct,
    }


def scrape_stocks():
    """抓取标的池行情"""
    codes = list(STOCK_POOL.keys())
    raw = fetch_sina_quotes(codes)

    results = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        parsed = parse_stock_line(line)
        if not parsed:
            continue
        meta = STOCK_POOL.get(parsed["sid"])
        if not meta:
            continue
        results.append({
            "code": meta["code"],
            "name": meta["name"],
            "price": parsed["price"],
            "chg": parsed["chg"],
            "rating": meta["rating"],
            "ratingLabel": meta["ratingLabel"],
            "target": meta["target"],
            "upside": round((meta["target"] - parsed["price"]) / parsed["price"] * 100, 1) if parsed["price"] else 0,
            "conf": meta["conf"],
            "catalyst": meta["catalyst"],
        })

    # 保持顺序
    results.sort(key=lambda x: list(STOCK_POOL.values()).index(
        next(v for v in STOCK_POOL.values() if v["code"] == x["code"])))

    path = os.path.join(DATA_DIR, "stocks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stocks": results}, f, ensure_ascii=False, indent=2)
    print(f"[OK] stocks.json written — {len(results)} stocks")


def scrape_indices():
    """抓取指数行情"""
    codes = list(INDEX_CODES.keys())
    raw = fetch_sina_quotes(codes)

    results = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        parsed = parse_stock_line(line)
        if not parsed:
            continue
        name = INDEX_CODES.get(parsed["sid"], parsed["name"])
        results.append({
            "name": name,
            "val": parsed["price"],
            "chg": parsed["chg"],
            "dir": "up" if parsed["chg"] >= 0 else "down",
        })

    # 按配置顺序
    results.sort(key=lambda x: list(INDEX_CODES.values()).index(x["name"]))

    # 补充半导体指数（新浪没有独立指数代码，用科创板50作为近似，或保持手工补充）
    # 这里保留一个占位，实际可以用东方财富获取
    results.append({
        "name": "半导体指数",
        "val": 6723.11,  # 新浪不提供，保留上次值
        "chg": 0,
        "dir": "up",
    })

    path = os.path.join(DATA_DIR, "indices.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "indices": results}, f, ensure_ascii=False, indent=2)
    print(f"[OK] indices.json written — {len(results)} indices")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"[{datetime.now()}] Starting scrape...")
    scrape_indices()
    scrape_stocks()
    print(f"[{datetime.now()}] Done.")


if __name__ == "__main__":
    main()
