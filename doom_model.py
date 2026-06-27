"""Doomsday probability model.

Philosophy (per the 'honest, not 99%' design): the world ending TODAY is a priori
near-zero, so we start from a tiny base rate and only let genuinely ANOMALOUS,
high-severity factors push it up. Each factor i has:
  - a_i  in [0,1]: how abnormal it is today vs its normal level
  - w_i  in [0,1]: its severity ceiling (extinction-level ~0.9, local disaster ~0.05-0.15)
Aggregate via a noisy-OR, then the maneki-neko's luck shaves it down:
  P = (1 - (1-b) * prod(1 - a_i*w_i)) * (1 - luck)

Hard factors come from real APIs (signals.py); soft factors are scored 0-1 by Gemini
reading today's situation. A handful are anchors / easter eggs.
"""
import json
import math

BASE_RATE = 0.008  # ~0.8% prior that the world ends on any given day, before evidence
SOFT_FLOOR = 0.14  # chronic tension is "normal"; only deviation ABOVE this counts as anomaly


def sigmoid(x, center, scale):
    return 1.0 / (1.0 + math.exp(-(x - center) / scale))


# ---- hard-factor anomaly functions (take the merged signals dict) ----
def a_earthquake(d):
    m = (d.get("global_quake") or {}).get("max_mag") or 0
    return round(sigmoid(m, 7.6, 0.55), 3)  # M6.5->~0.12, M7.2->0.32, M8->0.77 (replay-friendly)

def a_tsunami(d):
    return 0.5 if (d.get("global_quake") or {}).get("tsunami") else 0.0

def a_asteroid(d):
    ast = d.get("asteroids") or {}
    ld = ast.get("closest_ld")
    if ld is None:
        return 0.0
    a = 1.0 / (1.0 + math.exp((ld - 1.5) / 0.8))   # 1.5LD->0.5, 6.7LD->~0.001
    if ast.get("hazardous") and ld < 10:
        a += 0.04
    return round(min(1.0, a), 3)

def a_solar(d):
    sw = d.get("space_weather") or {}
    scale = (sw.get("max_scale") or 0) / 5.0
    fl = str(sw.get("flare") or "")
    flare = 0.6 if fl.startswith("X") else 0.3 if fl.startswith("M") else 0.05
    return round(min(1.0, scale * 0.7 + flare * 0.5), 3)

def a_typhoon(d):
    # only super-typhoon territory counts; normal TS in the W-Pacific is "平常" -> 0
    tp = d.get("typhoon") or {}
    return round(max(0.0, ((tp.get("maxcat") or 0) - 3) / 2.0), 3)  # TS(3)->0, STS(4)->0.5, TY(5)->1

def a_wildfire(d):
    wf = d.get("wildfire") or {}
    n = wf.get("count")
    return round(sigmoid(n, 25000, 8000), 3) if n else 0.0

def a_media(d):
    n = (d.get("doom_news") or {}).get("count") or 0
    return round(min(0.6, n / 75.0 * 0.6), 3)


# factor registry: (key, label, group, weight w, kind, anomaly_fn or soft_key)
HARD = [
    ("earthquake", "地殻変動・大地震", "地球物理", 0.12, a_earthquake),
    ("tsunami", "津波", "地球物理", 0.08, a_tsunami),
    ("asteroid", "天体衝突", "宇宙天体", 0.92, a_asteroid),
    ("solar", "太陽嵐・フレア", "宇宙天体", 0.12, a_solar),
    ("typhoon", "巨大台風", "気候天気", 0.05, a_typhoon),
    ("wildfire", "大規模森林火災", "気候天気", 0.05, a_wildfire),
    ("media", "メディア騒乱度", "地政学", 0.06, a_media),
]
SOFT = [
    ("nuclear", "核戦争・核緊張", "地政学", 0.55),
    ("conflict", "武力紛争の激化", "地政学", 0.16),
    ("pandemic", "新興感染症", "地政学", 0.35),
    ("agi", "AGI/AIの暴走", "技術", 0.42),
    ("cyber", "重要インフラ崩壊", "技術", 0.10),
    ("unrest", "政治経済の不安定", "地政学", 0.07),
    ("climate", "気候崩壊・異常気象", "気候天気", 0.10),
]
ANCHOR = [  # (key, label, group, w, a)  -- mostly flavor / can't-predict
    ("grb", "ガンマ線バースト", "宇宙天体", 0.95, 0.004),
    ("supervolcano", "超巨大火山噴火", "地球物理", 0.85, 0.004),
    ("alien", "地球外接触", "宇宙天体", 0.60, 0.002),
]


def score_one_soft(client, model, key, label):
    """ULTRA: one dedicated deep agent (search-grounded + thinking) scores ONE soft factor."""
    from google.genai import types
    prompt = (f"あなたは地球規模の破滅リスクの専門アナリストにゃ。『{label}』という破滅リスク要因だけを担当し、"
              "今日の世界情勢・最新ニュースを深く分析するにゃ。その『急性異常度』を 0.0(完全に平常)〜1.0(差し迫った危機) "
              "で採点するにゃ。慢性的な状態は『平常運転』として 0 に近く、今日 新たに急性悪化した場合のみ高得点にゃ。"
              'JSONだけ返すにゃ: {"a":0.0,"note":"根拠(日本語25字)"}')
    try:
        r = client.models.generate_content(model=model, contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5, max_output_tokens=800,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                thinking_config=types.ThinkingConfig(thinking_budget=256)))
        txt = r.text or ""
        o = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
        return {"a": max(0.0, min(1.0, float(o["a"]))), "note": o.get("note", "")}
    except Exception:
        return {"a": 0.1, "note": "(分析失敗)"}


def score_soft_factors(client, model, budget=0):
    """One Gemini call scores all soft factors 0-1 from today's world situation.
    Tries Google Search grounding first (news-based), falls back to ungrounded.
    budget>0 enables deeper reasoning (PRO mode)."""
    from google.genai import types
    keys = ", ".join(f'"{k}"' for k, *_ in SOFT)
    labels = "\n".join(f"- {k}: {lbl}" for k, lbl, *_ in SOFT)
    prompt = ("あなたは地球規模の破滅リスク(global catastrophic risk)の専門アナリストにゃ。\n"
              "採点するのは『今日、世界の終焉に向けて どれだけ「急性の」異常があるか』にゃ。重要な基準:\n"
              "・慢性的な状態(進行中の戦争、核保有国の対立、AI開発競争、気候変動)は「平常運転」として 0.0〜0.05 にするにゃ。\n"
              "・ほとんどの日は全項目 0.0〜0.10 のはずにゃ。通常レベルのニュース(局地戦闘・外交緊張・熱波)でも 0.05〜0.15 にゃ。\n"
              "・0.5以上を付けるのは、今日まさに世界規模の破局に直結する「新規の急性事態」(核ミサイル発射命令、致死率の高い"
              "新型パンデミックの世界的拡大、AGIの制御喪失、確認された衝突天体など)が起きた場合だけにゃ。\n"
              "最新ニュースを踏まえつつ、上の基準で厳しめに、低めに採点するにゃ。\n\n" + labels +
              '\n\n次のJSONだけ返すにゃ(他の文字禁止): {' +
              ", ".join(f'"{k}":{{"a":0.0,"note":"短い根拠(日本語20字)"}}' for k, *_ in SOFT) + "}")

    def _call(use_search):
        cfg_kw = dict(temperature=0.6, max_output_tokens=900 + budget,
                      thinking_config=types.ThinkingConfig(thinking_budget=budget))
        if use_search:
            cfg_kw["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        else:
            cfg_kw["response_mime_type"] = "application/json"
        r = client.models.generate_content(model=model, contents=prompt,
                                            config=types.GenerateContentConfig(**cfg_kw))
        txt = r.text or ""
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])

    for use_search in (True, False):
        try:
            o = _call(use_search)
            return {k: {"a": max(0.0, min(1.0, float(o[k]["a"]))), "note": o[k].get("note", ""),
                        "grounded": use_search}
                    for k, *_ in SOFT if k in o}
        except Exception:
            continue
    return {k: {"a": 0.1, "note": "(評価不能)", "grounded": False} for k, *_ in SOFT}


def compute(signals_data, soft_scores, luck):
    factors = []
    for key, label, group, w, fn in HARD:
        a = fn(signals_data)
        factors.append({"key": key, "label": label, "group": group, "a": a, "w": w,
                        "contribution": round(a * w, 4), "kind": "hard"})
    for key, label, group, w in SOFT:
        s = soft_scores.get(key, {"a": 0.1, "note": ""})
        a_raw = round(s["a"], 3)
        a = round(max(0.0, (a_raw - SOFT_FLOOR) / (1 - SOFT_FLOOR)), 3)  # subtract chronic floor
        factors.append({"key": key, "label": label, "group": group, "a": a, "a_raw": a_raw, "w": w,
                        "contribution": round(a * w, 4), "kind": "gemini", "note": s.get("note", "")})
    for key, label, group, w, a in ANCHOR:
        factors.append({"key": key, "label": label, "group": group, "a": a, "w": w,
                        "contribution": round(a * w, 4), "kind": "anchor"})

    prod = (1.0 - BASE_RATE)
    for f in factors:
        prod *= (1.0 - f["a"] * f["w"])
    p_raw = 1.0 - prod
    p = p_raw * (1.0 - luck)
    factors.sort(key=lambda f: -f["contribution"])
    return {
        "probability": round(p * 100, 2),
        "probability_raw": round(p_raw * 100, 2),
        "base_rate": BASE_RATE, "luck": round(luck, 3),
        "factors": factors,
    }


if __name__ == "__main__":
    import os
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "hacktokyo")
    from google import genai
    import signals
    client = genai.Client(vertexai=True, project="hacktokyo", location="global")
    data = signals.fetch_all()
    soft = score_soft_factors(client, "gemini-3.5-flash")
    out = compute(data, soft, luck=0.15)
    print(f"FINAL: {out['probability']}%  (raw {out['probability_raw']}%, luck {out['luck']})")
    for f in out["factors"][:10]:
        note = f.get("note", "")
        print(f"  {f['contribution']:.3f}  {f['label']:<16} a={f['a']:.2f} w={f['w']:.2f} [{f['kind']}] {note}")
