"""Discover a working (location, model) combo for Gemini on Vertex AI using ADC."""
import os, sys
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "hacktokyo")
from google import genai

PROJECT = "hacktokyo"
LOCATIONS = ["global", "us-central1"]
MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-001", "gemini-3.5-flash-preview",
          "gemini-2.5-flash", "gemini-flash-latest"]

for loc in LOCATIONS:
    try:
        client = genai.Client(vertexai=True, project=PROJECT, location=loc)
    except Exception as e:
        print(f"[client loc={loc}] ERROR: {str(e)[:160]}"); continue
    for m in MODELS:
        try:
            r = client.models.generate_content(model=m, contents="Reply with exactly: OK")
            print(f"\n✅ WORKS  loc={loc}  model={m}  ->  {r.text!r}")
            sys.exit(0)
        except Exception as e:
            print(f"  ✗ loc={loc} model={m}: {str(e)[:150]}")
print("\n❌ none of the combos worked")
