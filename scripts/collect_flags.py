# -*- coding: utf-8 -*-
"""Collect rental/accident flags from Encar detail + record APIs (via CDP page context)."""
import json, sys, time, urllib.request, websocket

BASE = "http://127.0.0.1:9222"
SRC = r"C:/Users/cnd63/AppData/Local/Temp"
BATCH = 20

def get_target():
    ts = [x for x in json.load(urllib.request.urlopen(BASE + "/json", timeout=5)) if x.get("type") == "page"]
    return next((x for x in ts if "fem.encar.com" in x.get("url", "")), None)

def ev(expr, timeout=60):
    t = get_target()
    if not t: raise RuntimeError("no page")
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=timeout)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                return m.get("result", {}).get("result", {}).get("value")
    finally:
        try: ws.close()
        except Exception: pass

def batch_fetch(urls, extract):
    """urls: list; extract: JS arrow body string receiving r (response) -> value."""
    parts = []
    for u in urls:
        parts.append("fetch(%s).then(async r=>r.status===200?await r.json():null).then(j=>%s).catch(e=>null)" % (json.dumps(u), extract))
    expr = "Promise.all([%s]).then(a=>JSON.stringify(a))" % ",".join(parts)
    for attempt in range(3):
        try:
            out = ev(expr)
            if out: return json.loads(out)
        except Exception:
            pass
        time.sleep(1.0)
    return [None] * len(urls)

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def unique_listings(key):
    d = json.load(open(f"{SRC}/encar_{key}.json", encoding="utf-8"))
    seen, out = set(), []
    for r in d["items"]:
        lid = str(r[0])
        if lid in seen: continue
        seen.add(lid)
        out.append({"id": lid, "badge": r[2] or ""})
    return out

def collect(key):
    items = unique_listings(key)
    print(key, "listings:", len(items), flush=True)
    # 1) listing -> vehicleId
    vids = {}
    for ch in chunks([x["id"] for x in items], BATCH):
        urls = [f"https://api.encar.com/v1/readside/vehicle/{lid}" for lid in ch]
        res = batch_fetch(urls, "({vid:j&&j.vehicleId})")
        for lid, r in zip(ch, res):
            if r and r.get("vid"): vids[lid] = str(r["vid"])
        time.sleep(0.05)
    print(key, "vehicleIds:", len(vids), flush=True)
    # 2) record
    out = {}
    ids = list(vids.items())
    for ch in chunks(ids, BATCH):
        urls = [f"https://api.encar.com/v1/readside/record/vehicle/{vid}/open" for _, vid in ch]
        res = batch_fetch(urls, "({a:j?j.accidentCnt:null,m:j?j.myAccidentCnt:null,o:j?j.otherAccidentCnt:null,"
                               "mc:j?j.myAccidentCost:null,oc:j?j.otherAccidentCost:null,tl:j?j.totalLossCnt:null,"
                               "fl:j?j.floodTotalLossCnt:null,th:j?j.robberCnt:null,ow:j?j.ownerChangeCnt:null,"
                               "u1:j?j.carInfoUse1s:null,use:j?j.use:null})")
        for (lid, vid), r in zip(ch, res):
            badge = next(x["badge"] for x in items if x["id"] == lid)
            rental = ("렌터카" in badge) or bool(r and r.get("u1") and "3" in [str(x) for x in r["u1"]])
            acc = int((r or {}).get("a") or 0)
            out[lid] = {
                "vehicle_id": vid,
                "rental": rental,
                "accident": acc > 0 or int((r or {}).get("m") or 0) > 0 or int((r or {}).get("o") or 0) > 0,
                "accident_cnt": acc,
                "my_cnt": int((r or {}).get("m") or 0),
                "other_cnt": int((r or {}).get("o") or 0),
                "my_cost": int((r or {}).get("mc") or 0),
                "other_cost": int((r or {}).get("oc") or 0),
                "total_loss": int((r or {}).get("tl") or 0) > 0,
                "flood": int((r or {}).get("fl") or 0) > 0,
                "theft": int((r or {}).get("th") or 0) > 0,
                "owner_changes": int((r or {}).get("ow") or 0),
                "record_ok": bool(r),
            }
        time.sleep(0.05)
    json.dump(out, open(f"{SRC}/flags_{key}.json", "w", encoding="utf-8"), ensure_ascii=False)
    ok = sum(1 for v in out.values() if v["record_ok"])
    rent = sum(1 for v in out.values() if v["rental"])
    acc = sum(1 for v in out.values() if v["accident"])
    print(f"{key} DONE records={len(out)} ok={ok} rental={rent} accident={acc}", flush=True)

if __name__ == "__main__":
    for key in sys.argv[1:]:
        collect(key)
