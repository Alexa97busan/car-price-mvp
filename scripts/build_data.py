# -*- coding: utf-8 -*-
"""Build public data files for the Renault used-car fair-price calculator.

Sources (local, private snapshots):
  - encar_{MODEL}.json : Encar search API snapshots (2026-11-21)
  - sample300_QM6.json / sample300_SM6.json / sample_{MODEL}.json : option samples
  - encar_options_standard.json : option dictionary

Outputs:
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

FUEL_MAP = {
    "가솔린": "gasoline", "디젤": "diesel", "LPG(일반인 구입)": "lpg",
    "가솔린+전기": "hybrid", "가솔린+LPG": "hybrid", "가솔린+LPi": "hybrid",
    "전기": "ev",
}
FUEL_LABEL = {"gasoline": "가솔린", "diesel": "디젤", "lpg": "LPG",
              "hybrid": "하이브리드", "ev": "전기", "other": "기타"}

TRIM_TOKENS = ["프리미에르", "인스파이어", "퀘스트", "클래식", "RE", "LE", "SE", "PE", "필"]

def trim_of(badge):
    b = badge or ""
    for t in TRIM_TOKENS:
        if t in b:
            return t
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
        counts[max(0, min(nb - 1, idx))] += 1
    step = (hi - lo) / nb
    return [{"from": round(lo + i * step), "to": round(lo + (i + 1) * step), "count": c}
            for i, c in enumerate(counts)]

def km_slope(rows):
    years = sorted({r["year"] for r in rows})
    if len(rows) < 30 or len(years) < 2: return None
    X, y = [], []
    for r in rows:
        X.append([1.0] + [1.0 if r["year"] == yv else 0.0 for yv in years[1:]] + [r["km"] / 10000.0])
        y.append(r["price"])
    beta, *_ = np.linalg.lstsq(np.array(X), np.array(y, dtype=float), rcond=None)
    return round(float(beta[-1]), 1)

MODELS = [
    {"key": "QM6", "name": "QM6", "new_price_ref": {"lpg": 2923},
     "new_price_note": "2026년형 LPe LE 2,797 / RE 3,049의 중앙값"},
    {"key": "SM6", "name": "SM6", "new_price_ref": {"lpg": 2980},
     "new_price_note": "SM6 LPe 신차가 LE 2,838 / RE 3,122의 중앙값(2023 기준)"},
    {"key": "XM3", "name": "XM3"},
    {"key": "SM3", "name": "SM3"},
    {"key": "SM5", "name": "SM5"},
    {"key": "SM7", "name": "SM7"},
    {"key": "QM3", "name": "QM3"},
    {"key": "ARKANA", "name": "아르카나"},
    {"key": "MASTER", "name": "마스터"},
    {"key": "QM5", "name": "QM5"},
    {"key": "CLIO", "name": "클리오"},
    {"key": "TWIZY", "name": "트위지"},
    {"key": "CAPTUR", "name": "캡처"},
    {"key": "ZOE", "name": "조에"},
]

stats_models = []
for m in MODELS:
    try:
        d = load(f"encar_{m['key']}.json")
    except FileNotFoundError:
        continue
    by_fuel = collections.defaultdict(list)
    for r in d["items"]:
        fk = FUEL_MAP.get(r[3], "other")
        by_fuel[fk].append(r)

    fuels = {}
    for fk, items in by_fuel.items():
        if len(items) < 10:
            continue
        seen, uniq = set(), []
        for r in items:
            k = (r[1], r[2], r[4], r[5], r[6])
            if k in seen: continue
            seen.add(k); uniq.append(r)
        rows = [{"badge": r[2], "year": int(r[4]) // 100, "km": int(r[5]), "price": int(r[6]), "trim": trim_of(r[2])}
                for r in uniq]

        years = {}
        for yv in sorted({r["year"] for r in rows}):
            rs = [r for r in rows if r["year"] == yv]
            if len(rs) < 3: continue
            prices = [r["price"] for r in rs]
            kms = [r["km"] for r in rs]
            trims = {}
            for tv in sorted({r["trim"] for r in rs}):
                tr = [r for r in rs if r["trim"] == tv]
                if len(tr) >= 5:
                    tp = [r["price"] for r in tr]; tk = [r["km"] for r in tr]
                    trims[tv] = {"n": len(tr), "median": round(statistics.median(tp)),
                                 "p25": round(pct(tp, 25)), "p75": round(pct(tp, 75)),
                                 "median_km": round(statistics.median(tk))}
            years[str(yv)] = {
                "n": len(rs), "median": round(statistics.median(prices)),
                "p25": round(pct(prices, 25)), "p75": round(pct(prices, 75)),
                "p10": round(pct(prices, 10)), "p90": round(pct(prices, 90)),
                "min": min(prices), "max": max(prices),
                "median_km": round(statistics.median(kms)),
                "mean_km": round(statistics.mean(kms)),
                "bins": hist_bins(prices), "trims": trims,
            }
        if not years: continue
        slope = km_slope(rows)
        fuels[fk] = {
            "label": FUEL_LABEL.get(fk, fk), "total": len(rows), "raw": len(items),
            "km_slope_per_10k": slope if slope is not None else -30.0,
            "years": years,
        }

    if not fuels: continue
    entry = {"key": m["key"], "name": m["name"], "fuels": fuels}
    if m.get("new_price_ref"):
        entry["new_price_ref"] = m["new_price_ref"]
        entry["new_price_note"] = m["new_price_note"]
    stats_models.append(entry)

# option take rates per model
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

SAMPLE_FILES = {"QM6": "sample300_QM6.json", "SM6": "sample300_SM6.json"}
rates = {}
for m in MODELS:
    fn = SAMPLE_FILES.get(m["key"], f"sample_{m['key']}.json")
    try:
        samples = load(fn)
    except FileNotFoundError:
        continue
    total = len(samples)
    codes = {}
    for code in DISPLAY_CODES:
        n = sum(1 for x in samples if code in (x.get("standard") or []))
        codes[code] = {"n": n, "pct": round(n / total * 100) if total else 0}
    rates[m["key"]] = {"total": total, "codes": codes}

options_out = {"codes": [{"code": c, "name": n} for c, n in DISPLAY_CODES.items()], "rates": rates}

meta = {
    "generated_at": "2026-11-21",
    "snapshot": "2026-11-21",
    "source": "엔카 실매물 (르노코리아 14개 모델, 중복 제거)",
    "notes": [
        "모든 금액은 판매자 등록가(호가) 기준이며 실계약가는 3~10% 낮을 수 있습니다.",
        "옵션은 가격 가산 없이 장착률 정보로만 표시합니다 (300대 분석 결과 양의 프리미엄 미확인).",
        "표본 10대 미만 연식은 신뢰도 낮음으로 표시됩니다.",
        "모델·연료별 표본이 적은 경우 계산 범위가 넓어질 수 있습니다.",
    ],
}

json.dump({"models": stats_models}, open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(options_out, open(os.path.join(OUT, "options.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("models:", len(stats_models))
for m in stats_models:
    fuels = ", ".join(f"{f['label']}:{f['total']}" for f in m["fuels"].values())
    print(m["key"], "|", fuels)
