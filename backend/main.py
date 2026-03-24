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

app = FastAPI(title="Tilawah Matching API")

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
MAX_AUDIO_BYTES = 1_000_000


# ── POST /identify ─────────────────────────────────────────────────────

@app.post("/identify")
@limiter.limit("10/minute")
async def identify(
    request:   Request,
    audio:     UploadFile = File(...),
    mime_type: str        = Form(default="audio/webm"),
):
    # 1. Read and size-check
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording too long. Please keep it under 15 seconds.")

    ext = "mp4" if "mp4" in mime_type else "webm"

    # 2. Write temp file so Whisper can read it
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        # 3. Transcribe with Whisper
        with open(tmp_path, "rb") as f:
            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ar",
                response_format="verbose_json",
                prompt="بسم الله الرحمن الرحيم، قل هو الله أحد، الله الصمد، قل أعوذ برب الفلق، قل أعوذ برب الناس",
                temperature=0.0,
            )
    finally:
        os.unlink(tmp_path)

    arabic_text = transcription.text.strip()
    print(f"Whisper heard: {arabic_text}")

    if not arabic_text:
        raise HTTPException(422, "No speech detected. Try recording a longer passage.")

    # 4. Strip tashkeel and split into words
    stripped = strip_tashkeel(arabic_text)
    stripped = re.sub(r'[،,؛;\.!؟?\-]', ' ', stripped)
    stripped = re.sub(r'\s+', ' ', stripped).strip()  # Replace punctuation with space
    words    = [w for w in stripped.split() if w]
    print(f"Stripped words: {words}")

    async with httpx.AsyncClient(timeout=10) as http:

        # ── Pass 1: try progressively shorter anchors (6 words down to 2) ──
        match_result = None
        for anchor_length in range(min(6, len(words)), 1, -1):
            anchor = " ".join(words[:anchor_length])
            print(f"Trying {anchor_length}-word anchor: {anchor}")

            resp = await http.get(
                f"{QURAN_API}/search",
                params={"q": anchor, "size": 5, "page": 1, "language": "en"},
            )
            if resp.status_code != 200:
                continue

            results = resp.json().get("search", {}).get("results", [])
            if results:
                match_result = results
                print(f"Matched on {anchor_length}-word anchor")
                break

        # ── Pass 2: try each individual word (skip words under 4 chars) ──
        if not match_result:
            print("Anchor passes failed — trying individual words")
            for word in words:
                if len(word) < 4:
                    continue
                print(f"Trying single word: {word}")
                resp = await http.get(
                    f"{QURAN_API}/search",
                    params={"q": word, "size": 10, "page": 1, "language": "en"},
                )
                if resp.status_code != 200:
                    continue
                results = resp.json().get("search", {}).get("results", [])
                if results:
                    match_result = results
                    print(f"Matched on single word: {word}")
                    break

# ── Pass 3: fallback to alquran.cloud with word-overlap scoring ──
        if not match_result:
            print("Trying alquran.cloud fallback API")
            
            # Collect all candidate matches across all words
            candidates = {}  # verse_key -> {count, data}
            
            for word in words:
                if len(word) < 4:
                    continue
                resp = await http.get(
                    f"https://api.alquran.cloud/v1/search/{word}/all/ar",
                )
                if resp.status_code != 200:
                    continue
                matches = resp.json().get("data", {}).get("matches", [])
                for m in matches:
                    key = f"{m['surah']['number']}:{m['numberInSurah']}"
                    if key not in candidates:
                        candidates[key] = {"count": 0, "data": m}
                    candidates[key]["count"] += 1

            if candidates:
                # Pick the verse that matched the most words
                best_key = max(candidates, key=lambda k: candidates[k]["count"])
                best     = candidates[best_key]
                print(f"Best overlap match: {best_key} ({best['count']} words matched)")
                match_result = [{
                    "verse_key": best_key,
                    "text":      best["data"].get("text", ""),
                }]


        if not match_result:
            raise HTTPException(404, "Verse not found. Try recording a different passage.")

        verse_key       = match_result[0]["verse_key"]
        surah_num, ayah = verse_key.split(":")
        print(f"Best match: {verse_key}")

        # 5. Fetch verse and surah details in parallel
        verse_resp, surah_resp = await asyncio.gather(
            http.get(
                f"{QURAN_API}/verses/by_key/{verse_key}",
                params={
                    "language":     "en",
                    "words":        "false",
                    "translations": "131",
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

    raw_translation = (verse_data.get("translations") or [{}])[0].get("text", "")
    translation     = strip_html(raw_translation)

    return {
        "verse_key":    verse_key,
        "surah":        int(surah_num),
        "ayah":         int(ayah),
        "surah_name":   surah_data.get("name_simple",  f"Surah {surah_num}"),
        "surah_arabic": surah_data.get("name_arabic",  ""),
        "arabic_text":  verse_data.get("text_uthmani", match_result[0].get("text", "")),
        "translation":  translation,
        "whisper_text": arabic_text,
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