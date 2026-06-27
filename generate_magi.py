"""Generate the two extra MAGI cats (ears-covered, mouth-covered) by EDITING the
existing style_term.png so all three are the same character in different poses."""
import os
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "hacktokyo")
from google import genai
from google.genai import types

c = genai.Client(vertexai=True, project="hacktokyo", location="global")
base = open("assets/style_term.png", "rb").read()

COMMON = (" Keep the EXACT same worn rusty enamel maneki-neko CRT-terminal cat, identical art style, "
          "same dark industrial workshop background, same large BLANK green-grey CRT screen on its belly. "
          "Front-facing, centered, square. No text, no numbers, no letters anywhere; the belly screen stays blank.")
JOBS = {
    "ears": "Edit this image. Change the pose so BOTH front paws press over its EARS (the Japanese "
            "'hear no evil' 聞かざる pose). Its eyes are OPEN and clearly visible." + COMMON,
    "mouth": "Edit this image. Change the pose so BOTH front paws (or a rusty metal plate) cover its MOUTH "
             "(the Japanese 'speak no evil' 言わざる pose). Its eyes are OPEN and visible, ears uncovered." + COMMON,
}

for k, p in JOBS.items():
    try:
        r = c.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[types.Part.from_bytes(data=base, mime_type="image/png"), p],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]))
        for part in (r.candidates[0].content.parts or []):
            d = getattr(part, "inline_data", None)
            if d and d.data:
                open(f"assets/term_{k}.png", "wb").write(d.data)
                print(k, "OK", len(d.data)); break
        else:
            print(k, "no image")
    except Exception as e:
        print(k, "ERR", str(e)[:160])
