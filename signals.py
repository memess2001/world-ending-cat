"""Fetch real-time 'doomsday signals' from free public APIs (all verified live 2026-06-27).
Every fetcher is defensive: short timeout, returns a safe default on any failure,
so a live demo never hangs or crashes.
"""
import datetime
import time
from concurrent.futures import ThreadPoolExecutor

import requests

TIMEOUT = 5
UA = {"User-Agent": "doomsday-maneki-neko/1.0 (hackathon demo)"}

SHINDO = {10: "1", 20: "2", 30: "3", 40: "4", 45: "5弱", 50: "5強",
          55: "6弱", 60: "6強", 70: "7", -1: "不明"}
KANTO = {"東京都", "神奈川県", "千葉県", "埼玉県", "茨城県", "群馬県", "栃木県"}


def get_global_earthquakes():
    try:
        r = requests.get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
                         timeout=TIMEOUT, headers=UA)
        feats = r.json().get("features", [])
        mags = [(f["properties"].get("mag"), f["properties"].get("place"),
                 f["properties"].get("tsunami", 0)) for f in feats
                if f["properties"].get("mag") is not None]
        if not mags:
            return {"max_mag": 0, "place": "静か", "count": 0, "tsunami": False}
        mags.sort(key=lambda x: x[0], reverse=True)
        top = mags[0]
        return {"max_mag": round(top[0], 1), "place": top[1] or "不明",
                "count": len(feats), "tsunami": any(m[2] for m in mags)}
    except Exception as e:
        return {"max_mag": None, "place": "取得失敗", "count": 0, "tsunami": False, "error": str(e)[:80]}


def get_japan_earthquakes():
    try:
        r = requests.get("https://api.p2pquake.net/v2/history",
                         params={"codes": 551, "limit": 10}, timeout=TIMEOUT, headers=UA)
        data = r.json()
        if not data:
            return {"max_mag": 0, "region": "静か", "shindo": "なし", "kanto": False}
        latest = data[0]
        eq = latest.get("earthquake", {})
        hypo = eq.get("hypocenter", {})
        scale = eq.get("maxScale", -1)
        prefs = {p.get("pref") for p in latest.get("points", [])}
        return {"max_mag": hypo.get("magnitude"), "region": hypo.get("name") or "不明",
                "shindo": SHINDO.get(scale, "不明"), "kanto": bool(prefs & KANTO)}
    except Exception as e:
        return {"max_mag": None, "region": "取得失敗", "shindo": "不明", "kanto": False, "error": str(e)[:80]}


def get_asteroids(api_key="DEMO_KEY"):
    try:
        today = datetime.date.today().isoformat()
        r = requests.get("https://api.nasa.gov/neo/rest/v1/feed",
                         params={"start_date": today, "end_date": today, "api_key": api_key},
                         timeout=TIMEOUT, headers=UA)
        data = r.json()
        neos = data.get("near_earth_objects", {}).get(today, [])
        if not neos:
            return {"count": 0, "closest_ld": None, "hazardous": False, "name": None}
        closest = min(neos, key=lambda n: float(n["close_approach_data"][0]["miss_distance"]["lunar"]))
        return {"count": data.get("element_count", len(neos)),
                "closest_ld": round(float(closest["close_approach_data"][0]["miss_distance"]["lunar"]), 1),
                "hazardous": any(n.get("is_potentially_hazardous_asteroid") for n in neos),
                "name": closest.get("name")}
    except Exception as e:
        return {"count": None, "closest_ld": None, "hazardous": False, "name": None, "error": str(e)[:80]}


def get_space_weather():
    out = {"kp": None, "max_scale": 0, "flare": None, "storm_text": "none"}
    try:
        s = requests.get("https://services.swpc.noaa.gov/products/noaa-scales.json",
                         timeout=TIMEOUT, headers=UA).json()
        day = s.get("0") or next(iter(s.values()), {})
        scales = []
        for k in ("G", "S", "R"):
            v = (day.get(k) or {}).get("Scale")
            scales.append(int(v) if v not in (None, "null") else 0)
        out["max_scale"] = max(scales) if scales else 0
        out["storm_text"] = (day.get("G") or {}).get("Text", "none")
    except Exception:
        pass
    try:
        kp = requests.get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
                          timeout=TIMEOUT, headers=UA).json()
        if len(kp) > 1:
            out["kp"] = round(float(kp[-1][1]), 1)
    except Exception:
        pass
    if out["kp"] is None:
        try:
            k2 = requests.get("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
                              timeout=TIMEOUT, headers=UA).json()
            if k2:
                out["kp"] = round(float(k2[-1].get("kp_index") or k2[-1].get("estimated_kp")), 1)
        except Exception:
            pass
    try:
        fl = requests.get("https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json",
                          timeout=TIMEOUT, headers=UA).json()
        rec = fl[0] if isinstance(fl, list) and fl else fl
        out["flare"] = rec.get("max_class") or rec.get("current_class")
    except Exception:
        pass
    return out


_gdelt_cache = {"t": 0, "data": None}


def _hn_doom_news():
    r = requests.get("https://hn.algolia.com/api/v1/search_by_date",
                     params={"query": "war OR nuclear OR pandemic OR catastrophe", "tags": "story",
                             "hitsPerPage": 20}, timeout=TIMEOUT, headers=UA)
    hits = r.json().get("hits", [])
    return {"count": len(hits), "sample": hits[0]["title"] if hits else None, "source": "HN"}


def get_doom_news():
    # GDELT limits to 1 req / 5s per IP -> cache 60s; fall back to HN Algolia if GDELT is empty.
    if _gdelt_cache["data"] and time.time() - _gdelt_cache["t"] < 60:
        return _gdelt_cache["data"]
    out = None
    try:
        q = '(war OR invasion OR nuclear OR pandemic OR catastrophe OR airstrike OR "state of emergency")'
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
                         params={"query": q, "mode": "ArtList", "format": "json",
                                 "maxrecords": 75, "timespan": "24h", "sort": "hybridrel"},
                         timeout=TIMEOUT, headers=UA)
        arts = r.json().get("articles", [])
        if arts:
            out = {"count": len(arts), "sample": arts[0]["title"], "source": "GDELT"}
    except Exception:
        out = None
    if not out:
        try:
            out = _hn_doom_news()
        except Exception as e:
            out = {"count": None, "sample": None, "error": str(e)[:80]}
    _gdelt_cache.update(t=time.time(), data=out)
    return out


def get_typhoon():
    # JMA bosai active tropical cyclones (CORS-ok, no auth). Empty list = no storms.
    try:
        r = requests.get("https://www.jma.go.jp/bosai/typhoon/data/targetTc.json",
                         timeout=TIMEOUT, headers=UA)
        arr = r.json()
        if not arr:
            return {"count": 0, "maxcat": 0, "names": []}
        catmap = {"LOW": 1, "TD": 2, "TS": 3, "STS": 4, "TY": 5}
        cats = [catmap.get(t.get("category"), 1) for t in arr]
        return {"count": len(arr), "maxcat": max(cats) if cats else 0,
                "names": [t.get("typhoonNumber") for t in arr]}
    except Exception as e:
        return {"count": 0, "maxcat": 0, "error": str(e)[:80]}


_all_cache = {"t": 0, "data": None}


def fetch_all(nasa_key="DEMO_KEY", ttl=60):
    """Run all fetchers in parallel; cache for `ttl`s so repeated spins are fast.
    Real-world signals barely change minute-to-minute, so a 60s cache is safe."""
    if _all_cache["data"] and time.time() - _all_cache["t"] < ttl:
        return _all_cache["data"]
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {
            "global_quake": ex.submit(get_global_earthquakes),
            "japan_quake": ex.submit(get_japan_earthquakes),
            "asteroids": ex.submit(get_asteroids, nasa_key),
            "space_weather": ex.submit(get_space_weather),
            "doom_news": ex.submit(get_doom_news),
            "typhoon": ex.submit(get_typhoon),
        }
        result = {k: f.result() for k, f in futs.items()}
    _all_cache.update(t=time.time(), data=result)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_all(), ensure_ascii=False, indent=2))
