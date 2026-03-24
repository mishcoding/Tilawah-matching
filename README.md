# Tilawah-matching — آية

Identify any Quranic verse by listening. Tap to record, Whisper transcribes the
Arabic, and the Quran Foundation API matches and returns the exact verse.

---

## Project structure

```
ayah/
├── backend/
│   ├── main.py            # FastAPI app — one POST /identify endpoint
│   ├── requirements.txt
│   ├── railway.toml       # Railway deployment config
│   └── .env.example       # Copy to .env and fill in your key
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── App.css
    │   ├── main.jsx
    │   └── components/
    │       ├── ListenButton.jsx
    │       └── VerseCard.jsx
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── vercel.json        # Vercel deployment config
```

---

## Local development

### Backend

```bash
cd backend
cp .env.example .env          # add your OPENAI_API_KEY
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload      # http://localhost:8000
```

Auto-generated API docs available at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

---

## Deployment

### Backend → Railway

1. Push repo to GitHub
2. Create new project on railway.app → Deploy from GitHub repo
3. Point root directory to `/backend`
4. Add environment variables in Railway dashboard:
   - `OPENAI_API_KEY` = your key
   - `FRONTEND_URL` = your Vercel URL (add after frontend is deployed)
5. Railway uses `railway.toml` to start the server automatically

### Frontend → Vercel

1. Create new project on vercel.com → Import GitHub repo
2. Set root directory to `/frontend`
3. Add environment variable:
   - `VITE_BACKEND_URL` = your Railway URL
4. Deploy

---

## Cost control

Whisper costs $0.006/minute of audio.
- A 10-second recording = ~$0.001
- 1,000 recordings = ~$1.00

The backend enforces:
- 10 requests per IP per minute (slowapi rate limiter)
- 1 MB max upload size (~15 seconds of audio)

Set a hard monthly spend cap at platform.openai.com → Settings → Limits.

---

## APIs used

- **OpenAI Whisper** — Arabic speech-to-text (`whisper-1`, `language=ar`)
- **Quran Foundation** — verse search, full text, translations, surah metadata
  (`api.qurancdn.com/api/qdc`)
