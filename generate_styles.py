"""Generate a few maneki-neko slot-machine style options via Gemini Nano Banana.
Each leaves a BLANK belly display panel so the live reels + % can be overlaid."""
import os, sys
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "hacktokyo")
from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="hacktokyo", location="global")
MODEL = "gemini-3-pro-image-preview"
os.makedirs("assets", exist_ok=True)

COMMON = (" Front-facing, symmetrical maneki-neko (lucky cat) shaped like a slot machine. "
          "One paw raised like a slot-machine lever. A LARGE BLANK rounded display panel on its belly, "
          "completely empty (a number will be added later). Centered square composition, high detail. "
          "IMPORTANT: no text, no numbers, no words, no letters anywhere; keep the belly panel blank.")

STYLES = {
    "kawaii": "Adorable kawaii pastel illustration, soft chunky rounded shapes, gold bell and red collar, "
              "gold koban coin, sparkles, cute and friendly, clean soft studio background.",
    "showa": "Retro Showa-era Japanese gacha/pachinko aesthetic, warm vintage muted colors, aged-paper texture, "
             "nostalgic lucky-charm vibe, cozy old shotengai background.",
    "neon": "Neon cyberpunk vaporwave style, glowing magenta and cyan, dark moody background, holographic, "
            "futuristic arcade machine, glowing lever, dark glass belly panel.",
}

for name, style in STYLES.items():
    try:
        r = client.models.generate_content(
            model=MODEL, contents=style + COMMON,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]))
        saved = False
        for p in (r.candidates[0].content.parts or []):
            if getattr(p, "inline_data", None) and p.inline_data.data:
                fn = f"assets/style_{name}.png"
                with open(fn, "wb") as f:
                    f.write(p.inline_data.data)
                print(f"✅ {name}: {fn} ({len(p.inline_data.data)} bytes)")
                saved = True
                break
        if not saved:
            print(f"  ~ {name}: no image returned")
    except Exception as e:
        print(f"  ✗ {name}: {str(e)[:140]}")
