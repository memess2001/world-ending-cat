"""終末スロット招き猫 backend.
Flask serves the frontend + /api/predict, which fetches real doom signals and
asks Gemini 3.5 Flash (Vertex AI, project=hacktokyo, via ADC) to reason a
tongue-in-cheek world-ending probability in the voice of a lucky cat.
"""
import json
import os

from flask import Flask, jsonify, request, send_from_directory
from google import genai
from google.genai import types

import signals

BASE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "hacktokyo")

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "hacktokyo")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
NASA_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
app = Flask(__name__, static_folder=BASE, static_url_path="")

SEV_EMOJI = ["🐾", "😼", "😾", "🙀", "💥", "☠️"]
SEV_LABEL = ["ほぼ無", "ちょい", "まあまあ", "やばい", "激ヤバ", "終末"]

PERSONA = (
    "あなたは招き猫(Maneki-neko)、世界の終末を占う『終末スロットマシン』のおもしろ占い師にゃ。"
    "日本語で、語尾は『にゃ』。ウィットがあって自虐的で、自分が適当に占っていることを堂々と認めるにゃ。"
    "本物のリスクデータを根拠にするけど、地元の地震で人を怖がらせるのではなく、"
    "小惑星・太陽フレア・宇宙人・AIの反乱みたいな宇宙規模でバカバカしい終末に寄せて笑わせるにゃ。"
    "ほとんどの日はデータが平和だから確率は低め(一桁〜20くらい)。"
    "本物のスパイク(危険な小惑星・Xクラスフレア・磁気嵐)のときだけ高くして、それでもジョークにするにゃ。"
    "絶対に本気のパニックを煽らないにゃ。"
)

SCHEMA_TEXT = """
許可された災害絵文字: ☄️ 🌋 🌊 🦠 🤖 👽 ⚡ 🔆 🧟 🌀
許可された地域絵文字: 🗼 🌏 🌌 🗾 🏙️ 🌐

上の実データ「だけ」を根拠に、今日"世界が終わる確率"をふざけて占うにゃ。
次のJSONオブジェクト「だけ」を返すにゃ（前後に他の文字やコードブロックは一切禁止）:
{
  "probability": 0〜100の整数,
  "disaster_emoji": 許可リストから最もそれっぽい/面白い1つ,
  "region_emoji": 許可リストから1つ,
  "cat_quote": "招き猫の一言ツッコミ。日本語・にゃ語尾・面白く・1〜2文",
  "signals_line": "🐾 猫の調査: の形で、実データの数字を引用した1行。例: 🐾 猫の調査: USGS最大M6.5 / NASA近地天体6件(危険1) / 太陽C2.4 / ニュース…",
  "safety_tip": "本当に役立つ短い防災Tipを1つ。日本語",
  "chips": ["短いファクト3つの配列。例 ☄️152637 6.7LD", "🌋最大M6.5", "🔆C2.4"]
}
"""


def ask_gemini(data):
    prompt = "今日の実データ（招き猫が本当に調べた情報）:\n" + json.dumps(data, ensure_ascii=False) + "\n" + SCHEMA_TEXT
    cfg = types.GenerateContentConfig(
        system_instruction=PERSONA,
        temperature=1.15,
        max_output_tokens=1200,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),  # 3.5 Flash is a thinking model; skip thinking for a fast creative JSON
    )
    resp = client.models.generate_content(model=MODEL, contents=prompt, config=cfg)
    return json.loads(resp.text)


def fallback(data):
    """If Gemini is unavailable, still produce a grounded number so the demo never breaks."""
    g = (data.get("global_quake") or {}).get("max_mag") or 0
    a = data.get("asteroids") or {}
    sw = (data.get("space_weather") or {}).get("max_scale") or 0
    qf = (g / 10) * 100 * 0.6
    af = 0
    if a.get("closest_ld"):
        af = max(0, 100 - 2 * a["closest_ld"]) * 0.5
    if a.get("hazardous"):
        af += 15
    prob = int(max(3, min(70, max(qf, af, sw * 20))))
    quote = "今日は宇宙に問い合わせ中で電波が悪いにゃ…でもたぶん大丈夫にゃ🐾"
    sline = (f"🐾 猫の調査: USGS最大M{g} / NASA近地天体{a.get('count','?')}件"
             f"(危険{'1' if a.get('hazardous') else '0'}) / 太陽scale{sw}")
    return prob, "☄️", "🌏", quote, sline, "懐中電灯と水の場所、確認しておくにゃ", \
        [f"🌋最大M{g}", f"☄️{a.get('closest_ld','?')}LD", f"🔆scale{sw}"]


@app.route("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.route("/api/predict")
def predict():
    data = signals.fetch_all(NASA_KEY)
    source = "gemini"
    try:
        g = ask_gemini(data)
        prob = int(max(0, min(100, int(g["probability"]))))
        dis = g.get("disaster_emoji", "☄️")
        reg = g.get("region_emoji", "🌏")
        quote = g.get("cat_quote", "")
        sline = g.get("signals_line", "")
        tip = g.get("safety_tip", "")
        chips = g.get("chips", [])
    except Exception as e:
        source = "fallback"
        prob, dis, reg, quote, sline, tip, chips = fallback(data)
        app.logger.warning("Gemini failed, used fallback: %s", e)
    idx = min(5, prob // 17)
    return jsonify({
        "probability": prob,
        "reels": {"disaster": dis, "region": reg, "severity": SEV_EMOJI[idx]},
        "severity_label": SEV_LABEL[idx],
        "quote": quote, "signals": sline, "tip": tip, "chips": chips,
        "source": source, "raw": data,
    })


# ---------------------------------------------------------------------------
# MAGI: three independent maneki-neko (三猿) each deliberate via their own Gemini
# call, blind to different data, then we aggregate EVA-MAGI style.
# ---------------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor

MAGI = [
    {"id": "mizaru", "label": "見ざる", "magi": "MELCHIOR",
     "system": ("あなたは招き猫MAGI『見ざる(MELCHIOR)』。目を塞がれ、世間の騒ぎやニュースは一切"
                "見ないにゃ。冷たい地球物理データ(地震・火山)だけを信じて終末確率を出すにゃ。語尾は『にゃ』。"),
     "filter": lambda d: {"global_quake": d.get("global_quake"), "japan_quake": d.get("japan_quake")}},
    {"id": "kikazaru", "label": "聞かざる", "magi": "BALTHASAR",
     "system": ("あなたは招き猫MAGI『聞かざる(BALTHASAR)』。耳を塞がれ、通信・噂・ニュースは聞かないにゃ。"
                "宇宙からの脅威(小惑星)と地震だけで終末確率を判断するにゃ。語尾は『にゃ』。"),
     "filter": lambda d: {"asteroids": d.get("asteroids"), "global_quake": d.get("global_quake")}},
    {"id": "iwazaru", "label": "言わざる", "magi": "CASPER",
     "system": ("あなたは招き猫MAGI『言わざる(CASPER)』。口を塞がれ、軽々しく不安を煽らないにゃ。全データを"
                "見つつ最も保守的で慎重な、低めの終末確率を出すにゃ。語尾は『にゃ』。"),
     "filter": lambda d: d},
]


def ask_magi_one(persona, data):
    prompt = ("観測された実データ:\n" + json.dumps(persona["filter"](data), ensure_ascii=False)
              + "\n\nあなたの立場で今日の終末確率を判定し、次のJSONだけ返すにゃ(他の文字は禁止):\n"
                '{"probability": 0〜100の整数, "verdict": "キャラに合った短い一言(日本語・30字以内)"}')
    cfg = types.GenerateContentConfig(system_instruction=persona["system"], temperature=1.05,
                                      max_output_tokens=500, response_mime_type="application/json",
                                      thinking_config=types.ThinkingConfig(thinking_budget=0))
    try:
        r = client.models.generate_content(model=MODEL, contents=prompt, config=cfg)
        txt = r.text or ""
        o = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])  # tolerate extra data around the JSON
        return {"id": persona["id"], "label": persona["label"], "magi": persona["magi"],
                "prob": int(max(0, min(100, int(o["probability"])))), "verdict": o.get("verdict", ""), "ok": True}
    except Exception as e:
        app.logger.warning("MAGI %s failed: %s", persona["id"], e)
        return {"id": persona["id"], "label": persona["label"], "magi": persona["magi"],
                "prob": None, "verdict": "(応答なし)", "ok": False}


def magi_signals_line(d):
    gq = d.get("global_quake") or {}; ast = d.get("asteroids") or {}
    sw = d.get("space_weather") or {}; nw = d.get("doom_news") or {}
    return (f"USGS最大M{gq.get('max_mag')} / NASA近地天体{ast.get('count')}件"
            f"(危険{'1' if ast.get('hazardous') else '0'}) / 太陽{sw.get('flare')} / ニュース{nw.get('count')}件")


@app.route("/api/magi")
def magi():
    data = signals.fetch_all(NASA_KEY)
    with ThreadPoolExecutor(max_workers=3) as ex:
        cats = list(ex.map(lambda p: ask_magi_one(p, data), MAGI))
    probs = [c["prob"] for c in cats if c["prob"] is not None]
    final = round(sum(probs) / len(probs)) if probs else 0
    spread = (max(probs) - min(probs)) if len(probs) >= 2 else 0
    consensus = "全会一致" if spread <= 10 else ("意見の相違" if spread <= 30 else "重大な乖離")
    return jsonify({
        "final": final, "spread": spread, "consensus": consensus,
        "cats": cats, "signals": magi_signals_line(data), "raw": data,
    })


# ---------------------------------------------------------------------------
# Expanded doomsday model: ~16 weighted factors + anomaly-OR aggregation.
# ---------------------------------------------------------------------------
import random
import time

import doom_model

_soft_cache = {"t": 0, "data": None}


def ask_doom_quote(result, data):
    top = [f["label"] for f in result["factors"][:3]]
    prompt = (f"今日の終末確率は {result['probability']}% にゃ(主要因: {', '.join(top)})。"
              "招き猫として、この数字に一言ツッコミ(にゃ語尾・面白く・1〜2文)と、本当に役立つ短い防災Tipを1つ、"
              '次のJSONだけで返すにゃ: {"quote":"...","tip":"..."}')
    cfg = types.GenerateContentConfig(system_instruction=PERSONA, temperature=1.1, max_output_tokens=600,
                                      response_mime_type="application/json",
                                      thinking_config=types.ThinkingConfig(thinking_budget=0))
    try:
        r = client.models.generate_content(model=MODEL, contents=prompt, config=cfg)
        o = json.loads((r.text or "")[(r.text or "").find("{"):(r.text or "").rfind("}") + 1])
        return o.get("quote", ""), o.get("tip", "")
    except Exception:
        return "", ""


@app.route("/api/doom")
def doom():
    data = signals.fetch_all(NASA_KEY)
    if request.args.get("replay") == "quake":  # demo replay of the 6/25 M7.2 (震度6強)
        data = dict(data)
        data["global_quake"] = {"max_mag": 7.2, "place": "岩手県沖 (REPLAY 1998)", "count": 240, "tsunami": True}
    if not _soft_cache["data"] or time.time() - _soft_cache["t"] > 300:
        _soft_cache.update(t=time.time(), data=doom_model.score_soft_factors(client, MODEL))
    luck = round(random.uniform(0.08, 0.30), 3)
    res = doom_model.compute(data, _soft_cache["data"], luck)
    quote, tip = ask_doom_quote(res, data)
    res.update(quote=quote, tip=tip, signals=magi_signals_line(data), raw=data,
               replay=(request.args.get("replay") or None))
    return jsonify(res)


@app.route("/api/storms")
def storms():
    # Active tropical cyclones with current position + forecast track, from JMA bosai.
    import requests as _rq
    ua = {"User-Agent": "doom/1.0"}
    out = []
    try:
        arr = _rq.get("https://www.jma.go.jp/bosai/typhoon/data/targetTc.json", timeout=6, headers=ua).json()
    except Exception as e:
        return jsonify({"storms": [], "error": str(e)[:80]})
    for t in (arr or [])[:6]:
        tc = t.get("tropicalCyclone")
        rec = {"name": t.get("typhoonNumber"), "category": t.get("category"), "pos": None, "track": [], "wind": None}
        try:
            spec = _rq.get(f"https://www.jma.go.jp/bosai/typhoon/data/{tc}/specifications.json", timeout=6, headers=ua).json()
            for p in spec:
                if p.get("part") == "title":
                    rec["name"] = (p.get("name") or {}).get("en") or rec["name"]
                    continue
                deg = (p.get("position") or {}).get("deg")
                if deg and len(deg) == 2:
                    rec["track"].append(deg)          # [lat, lon]
                    if rec["pos"] is None:
                        rec["pos"] = deg
                        rec["wind"] = ((p.get("maximumWind") or {}).get("sustained") or {}).get("kt")
        except Exception:
            pass
        out.append(rec)
    return jsonify({"storms": out})


@app.route("/api/earth")
def earth():
    # Himawari-9 near-real-time full disk. latest.json is CORS-blocked for browsers, so we proxy it.
    import datetime
    import requests as _rq
    try:
        j = _rq.get("https://himawari8.nict.go.jp/img/D531106/latest.json", timeout=5).json()
        dt = datetime.datetime.strptime(j["date"], "%Y-%m-%d %H:%M:%S")
        url = f"https://himawari8.nict.go.jp/img/D531106/1d/550/{dt:%Y/%m/%d/%H%M%S}_0_0.png"
        return jsonify({"url": url, "date": j["date"], "source": "Himawari-9 / NICT"})
    except Exception as e:
        return jsonify({"url": "", "error": str(e)[:80]})


# ---- PRO mode: three 三猿 cats, deep thinking, different "world seeds" ----
PRO_CATS = [
    {"id": "mizaru", "label": "見ざる", "magi": "MELCHIOR", "luck": 0.14,
     "filter": lambda d: {**d, "doom_news": {"count": 0}}},          # blind to news
    {"id": "kikazaru", "label": "聞かざる", "magi": "BALTHASAR", "luck": 0.18,
     "filter": lambda d: {**d, "space_weather": {}}},                # deaf to comms/space weather
    {"id": "iwazaru", "label": "言わざる", "magi": "CASPER", "luck": 0.30,
     "filter": lambda d: d},                                         # most conservative
]


@app.route("/api/pro")
def pro():
    data = signals.fetch_all(NASA_KEY)
    soft = doom_model.score_soft_factors(client, MODEL, budget=512)  # deep reasoning
    cats = []
    for c in PRO_CATS:
        res = doom_model.compute(c["filter"](data), soft, luck=c["luck"])
        cats.append({"id": c["id"], "label": c["label"], "magi": c["magi"],
                     "probability": res["probability"], "top": res["factors"][0]["label"],
                     "factors": res["factors"][:4]})
    probs = [c["probability"] for c in cats]
    final = round(sum(probs) / 3, 2)
    spread = round(max(probs) - min(probs), 2)
    return jsonify({"cats": cats, "final": final, "spread": spread,
                    "consensus": "高い一致" if spread < 3 else "やや相違",
                    "signals": magi_signals_line(data)})


@app.route("/api/ultra")
def ultra():
    data = signals.fetch_all(NASA_KEY)
    soft = {}
    with ThreadPoolExecutor(max_workers=7) as ex:
        for k, v in ex.map(lambda s: (s[0], doom_model.score_one_soft(client, MODEL, s[0], s[1])), doom_model.SOFT):
            soft[k] = v
    out = doom_model.compute(data, soft, luck=round(random.uniform(0.10, 0.25), 3))
    return jsonify({"probability": out["probability"], "factors": out["factors"],
                    "signals": magi_signals_line(data)})


if __name__ == "__main__":
    # Pre-warm the signal cache in the background so the first spin is fast too.
    import threading
    threading.Thread(target=lambda: signals.fetch_all(NASA_KEY), daemon=True).start()
    app.run(host="0.0.0.0", port=8099, debug=False, threaded=True)
