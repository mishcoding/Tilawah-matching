import asyncio
import os
import re
import tempfile

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

# ── App setup ──────────────────────────────────────────────────────────

app = FastAPI(title="Ayah API")

# Rate limiter — max 10 requests per IP per minute
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

client    = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
QURAN_API = "https://api.qurancdn.com/api/qdc"

# ~1 MB cap — plenty for a 15-second clip, blocks abuse
MAX_AUDIO_BYTES = 1_000_000


# ── POST /identify ─────────────────────────────────────────────────────
# Accepts: multipart form with `audio` (webm or mp4) and `mime_type`
# Returns: verse_key, surah, ayah, surah_name, arabic_text, translation

@app.post("/identify")
@limiter.limit("10/minute")
async def identify(
    request:   Request,
    audio:     UploadFile = File(...),
    mime_type: str        = Form(default="audio/webm"),
):
    # 1. Read and size-check the upload
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording too long. Please keep it under 15 seconds.")

    ext = "mp4" if "mp4" in mime_type else "webm"

    # 2. Write to a named temp file so Whisper can infer the audio format
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        # 3. Transcribe with Whisper ($0.006 / minute)
        with open(tmp_path, "rb") as f:
            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ar",
                response_format="verbose_json",
            )
    finally:
        os.unlink(tmp_path)

    arabic_text = transcription.text.strip()

    if not arabic_text:
        raise HTTPException(422, "No speech detected. Try recording a longer passage.")

    # 4. Strip tashkeel, build a 6-word search anchor
    stripped = strip_tashkeel(arabic_text)
    words    = stripped.split()
    anchor   = " ".join(words[:6])

    async with httpx.AsyncClient(timeout=10) as http:
        # 5. Search the Quran Foundation API
        search = await http.get(
            f"{QURAN_API}/search",
            params={"q": anchor, "size": 5, "page": 1, "language": "en"},
        )
        search.raise_for_status()
        results = search.json().get("search", {}).get("results", [])

        if not results:
            raise HTTPException(404, "Verse not found. Try recording a different passage.")

        verse_key        = results[0]["verse_key"]
        surah_num, ayah  = verse_key.split(":")

        # 6. Fetch full verse details and surah info in parallel
        verse_resp, surah_resp = await asyncio.gather(
            http.get(
                f"{QURAN_API}/verses/by_key/{verse_key}",
                params={
                    "language":     "en",
                    "words":        "false",
                    "translations": "131",   # Sahih International
                    "fields":       "text_uthmani",
                },
            ),
            http.get(
                f"{QURAN_API}/chapters/{surah_num}",
                params={"language": "en"},
            ),
        )

    verse_data = verse_resp.json().get("verse", {})
    surah_data = surah_resp.json().get("chapter", {})

    # Strip HTML footnote tags the API sometimes includes in translations
    raw_translation = (verse_data.get("translations") or [{}])[0].get("text", "")
    translation     = strip_html(raw_translation)

    return {
        "verse_key":    verse_key,
        "surah":        int(surah_num),
        "ayah":         int(ayah),
        "surah_name":   surah_data.get("name_simple",  f"Surah {surah_num}"),
        "surah_arabic": surah_data.get("name_arabic",  ""),
        "arabic_text":  verse_data.get("text_uthmani", results[0].get("text", "")),
        "translation":  translation,
        "whisper_text": arabic_text,  # returned for debugging; remove before v1 launch
    }


# ── GET /health ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}


# ── Helpers ────────────────────────────────────────────────────────────

def strip_tashkeel(text: str) -> str:
    """Remove Arabic diacritics (U+064B-U+065F) and tatweel (U+0640)."""
    return "".join(
        c for c in text
        if not ("\u064b" <= c <= "\u065f") and c != "\u0640"
    )


def strip_html(text: str) -> str:
    """Remove HTML tags from translation strings."""
    return re.sub(r"<[^>]+>", "", text)