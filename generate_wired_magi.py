"""Generate 3 covered-sense WIRED ASCII cats (見ざる/聞かざる/言わざる) by editing wired_cat.png
so they share the exact same green-phosphor Lain style."""
import os
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "hacktokyo")
from google import genai
from google.genai import types

c = genai.Client(vertexai=True, project="hacktokyo", location="global")
base = open("assets/wired_cat.png", "rb").read()
COMMON = (" Keep the EXACT same glowing green ASCII / wireframe maneki-neko on pure black, in the eerie "
          "Serial Experiments Lain / Wired phosphor-green line-art style. Front-facing, sitting, square. "
          "No text, no numbers, no letters anywhere.")
JOBS = {
    "eyes": "Edit this image. Change the pose so BOTH front paws are raised and pressed over its EYES "
            "(the 'see no evil' 見ざる pose)." + COMMON,
    "ears": "Edit this image. Change the pose so BOTH front paws are raised and cover its EARS "
            "(the 'hear no evil' 聞かざる pose). Eyes open and visible." + COMMON,
    "mouth": "Edit this image. Change the pose so a front paw covers its MOUTH "
             "(the 'speak no evil' 言わざる pose). Eyes open and visible." + COMMON,
}
for k, p in JOBS.items():
    try:
        r = c.models.generate_content(model="gemini-3-pro-image-preview",
            contents=[types.Part.from_bytes(data=base, mime_type="image/png"), p],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]))
        for part in (r.candidates[0].content.parts or []):
            d = getattr(part, "inline_data", None)
            if d and d.data:
                open(f"assets/wired_{k}.png", "wb").write(d.data)
                print(k, "OK", len(d.data)); break
        else:
            print(k, "no image")
    except Exception as e:
        print(k, "ERR", str(e)[:140])
