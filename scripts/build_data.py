# -*- coding: utf-8 -*-
"""Build public data files for the used-car fair-price calculator.

Sources (local, private snapshots):
  - encar_QM6.json / encar_SM6.json : Encar search API snapshots (2026-11-21)
  - sample300_QM6.json / sample300_SM6.json : 300 listings with options
  - encar_options_standard.json : Encar standard option dictionary

Outputs (public):
  - data/stats.json
  - data/options.json
  - data/meta.json
"""
import json, statistics, collections, os
import numpy as np

SRC = os.environ.get("ENCAR_SRC", r"C:/Users/cnd63/AppData/Local/Temp")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(OUT, exist_ok=True)

def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)

def trim_of(badge):
    b = badge or ""
    if "프리미에르" in b: return "프리미에르"
    if "퀘스트" in b: return "퀘스트"
    if "RE" in b: return "RE"
    if "LE" in b: return "LE"
    if "SE" in b: return "SE"
    if "PE" in b: return "PE"
    if "필" in b: return "필"
    return "기타"

def pct(v, q):
    return float(np.percentile(v, q))

def hist_bins(prices, nb=10):
    if not prices: return []
    lo, hi = pct(prices, 5), pct(prices, 95)
    if hi <= lo: hi = lo + 1
    counts = [0] * nb
    for p in prices:
        idx = int((p - lo) / (hi - lo) * nb)
        idx = max(0, min(nb - 1, idx))
        counts[idx] += 1
    step = (hi - lo) / nb
    return [{"from": round(lo + i * step), "to": round(lo + (i + 1) * step), "count": c} for i, c in enumerate(counts)]

def km_slope(rows):
    """price ~ year dummies + km, returns 만원 per km."""
    years = sorted({r["year"] for r in rows})
    if len(rows) < 30 or len(years) < 2: return None
    X = []
    y = []
    for r in rows:
        vec = [1.0] + [1.0 if r["year"] == yv else 0.0 for yv in years[1:]] + [r["km"] / 10000.0]
        X.append(vec); y.append(r["price"])
    beta, *_ = np.linalg.lstsq(np.array(X), np.array(y, dtype=float), rcond=None)
    return float(beta[-1])  # 만원 per 10,000km

MODELS = [
    {"key": "QM6", "name": "QM6 LPe", "short": "QM6", "fuel": "LPG", "body": "SUV",
     "new_price_ref": 2923, "new_price_note": "2026년형 LPe LE 2,797 / RE 3,049의 중앙값"},
    {"key": "SM6", "name": "SM6 LPe", "short": "SM6", "fuel": "LPG", "body": "세단",
     "new_price_ref": 2980, "new_price_note": "SM6 LPe 신차가 LE 2,838 / RE 3,122의 중앙값(2023 기준)"},
]

stats_models = []
all_years = collections.Counter()

for m in MODELS:
    d = load(f"encar_{m['key']}.json")
    lpg = [x for x in d["items"] if x[3].startswith("LPG")]
    seen, uniq = set(), []
    for r in lpg:
        k = (r[1], r[2], r[4], r[5], r[6])
        if k in seen: continue
        seen.add(k); uniq.append(r)
    rows = [{"badge": r[2], "ym": r[4], "year": r[4] // 100, "km": r[5], "price": r[6], "trim": trim_of(r[2])} for r in uniq]

    years = {}
    for yv in sorted({r["year"] for r in rows}):
        rs = [r for r in rows if r["year"] == yv]
        if len(rs) < 3:
            continue
        prices = [r["price"] for r in rs]
        kms = [r["km"] for r in rs]
        trims = {}
        for tv in sorted({r["trim"] for r in rs}):
            tr = [r for r in rs if r["trim"] == tv]
            if len(tr) >= 5:
                tp = [r["price"] for r in tr]
                tkm = [r["km"] for r in tr]
                trims[tv] = {"n": len(tr), "median": round(statistics.median(tp)),
                             "p25": round(pct(tp, 25)), "p75": round(pct(tp, 75)),
                             "median_km": round(statistics.median(tkm))}
        years[str(yv)] = {
            "n": len(rs),
            "median": round(statistics.median(prices)),
            "p25": round(pct(prices, 25)),
            "p75": round(pct(prices, 75)),
            "p10": round(pct(prices, 10)),
            "p90": round(pct(prices, 90)),
            "min": min(prices), "max": max(prices),
            "median_km": round(statistics.median(kms)),
            "mean_km": round(statistics.mean(kms)),
            "bins": hist_bins(prices),
            "trims": trims,
        }
        all_years[yv] += 1

    slope = km_slope(rows)
    stats_models.append({
        "key": m["key"], "name": m["name"], "fuel": m["fuel"], "body": m["body"],
        "new_price_ref": m["new_price_ref"], "new_price_note": m["new_price_note"],
        "total": len(rows), "raw": len(lpg),
        "km_slope_per_10k": round(slope, 1) if slope is not None else -30.0,
        "years": years,
    })

# options: take rates from 300 samples
DICT = load("encar_options_standard.json")
names = {}
def walk(o):
    if not isinstance(o, dict): return
    c = o.get("optionCd")
    if c and c not in names:
        names[c] = o.get("groupOptionName") or o.get("optionName")
    for s in (o.get("subOptions") or []): walk(s)
for o in DICT["options"]: walk(o)

DISPLAY_CODES = {
    "010": "선루프", "017": "알루미늄 휠", "020": "에어백(사이드)", "034": "통풍시트(운전석)",
    "051": "메모리 시트(운전석)", "057": "스마트키", "058": "후방 카메라", "059": "파워 전동 트렁크",
    "068": "크루즈 컨트롤(일반)", "074": "하이패스", "075": "헤드램프(LED)", "079": "크루즈 컨트롤(어댑티브)",
    "086": "후측방 경보 시스템", "088": "차선이탈 경보 시스템(LDWS)", "091": "마사지 시트",
    "094": "전자식 주차브레이크(EPB)", "095": "헤드업 디스플레이(HUD)",
}

samples = {}
for mg in ["QM6", "SM6"]:
    samples[mg] = load(f"sample300_{mg}.json")

options_out = {"codes": [], "take_rates": {}}
for code, disp in DISPLAY_CODES.items():
    rates = {}
    for mg in ["QM6", "SM6"]:
        ss = samples[mg]
        n = sum(1 for x in ss if code in (x.get("standard") or []))
        rates[mg] = {"n": n, "total": len(ss), "pct": round(n / len(ss) * 100) if ss else 0}
    options_out["codes"].append({"code": code, "name": disp})
    options_out["take_rates"][code] = rates

meta = {
    "generated_at": "2026-11-21",
    "snapshot": "2026-11-21",
    "source": "엔카 실매물 (LPG 일반인 구입, 중복 제거)",
    "notes": [
        "모든 금액은 판매자 등록가(호가) 기준이며 실계약가는 3~10% 낮을 수 있습니다.",
        "옵션은 가격 가산 없이 장착률 정보로만 표시합니다 (300대 분석 결과 양의 프리미엄 미확인).",
        "표본 10대 미만 연식은 신뢰도 낮음으로 표시됩니다.",
    ],
}

json.dump({"models": stats_models}, open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(options_out, open(os.path.join(OUT, "options.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written to", OUT)
for m in stats_models:
    print(m["key"], "total", m["total"], "years", sorted(m["years"]), "slope/10k", m["km_slope_per_10k"])
