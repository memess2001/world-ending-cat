"""Probe which image-generation model works on this Vertex project (Nano Banana / Imagen)."""
import os, sys
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "hacktokyo")
from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="hacktokyo", location="global")
PROMPT = ("A cute front-facing maneki-neko lucky cat, kawaii flat vector illustration, "
          "white cat with red collar and gold bell, one paw raised waving, centered, "
          "plain light background, clean sticker art")
os.makedirs("assets", exist_ok=True)


def save(b, name):
    with open(f"assets/{name}", "wb") as f:
        f.write(b)
    print(f"   SAVED assets/{name} ({len(b)} bytes)")


# 1) Gemini native image gen (Nano Banana family) via generate_content
for m in ["gemini-3-pro-image-preview", "gemini-3-flash-image", "nano-banana",
          "gemini-2.5-flash-image", "gemini-2.5-flash-image-preview"]:
    try:
        r = client.models.generate_content(
            model=m, contents=PROMPT,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]))
        got = False
        for p in (r.candidates[0].content.parts or []):
            if getattr(p, "inline_data", None) and p.inline_data.data:
                save(p.inline_data.data, "probe_gemini.png")
                print(f"✅ GEMINI IMAGE WORKS: {m}")
                got = True
                break
        if got:
            sys.exit(0)
        print(f"  ~ {m}: responded but no image part")
    except Exception as e:
        print(f"  ✗ gemini {m}: {str(e)[:120]}")

# 2) Imagen via generate_images
for m in ["imagen-4.0-fast-generate-001", "imagen-4.0-generate-001", "imagen-3.0-generate-002"]:
    try:
        r = client.models.generate_images(
            model=m, prompt=PROMPT, config=types.GenerateImagesConfig(number_of_images=1))
        save(r.generated_images[0].image.image_bytes, "probe_imagen.png")
        print(f"✅ IMAGEN WORKS: {m}")
        sys.exit(0)
    except Exception as e:
        print(f"  ✗ imagen {m}: {str(e)[:120]}")

print("❌ no image model worked on this project")
