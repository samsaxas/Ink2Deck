# Ink2Deck

Ink2Deck turns photos of whiteboards and handwritten notes into editable PowerPoint and PDF files.

The app is now a proper website with a separate backend and frontend:

- **Backend:** FastAPI (`backend/`), JSON API under `/api`
- **Frontend:** plain HTML, CSS and JavaScript (`frontend/`), served by the backend
- **Pages:** landing page (`/`), log in and sign up (`/login`), workspace (`/app`)

## How it works
1. Sign up or log in. Accounts are stored in MongoDB (same `Ink2Deck.users` collection as before, so existing accounts still work).
2. Upload a JPG, PNG or WebP photo (up to 10 MB). Drag and drop or paste also work.
3. Text is extracted only with Gemini vision from the original image. There is no local OCR fallback. If Gemini fails, the API returns a clear error.
4. Edit the text, then download a PowerPoint (title slide, original photo, one slide per paragraph) or a Unicode-safe PDF. Your edits are what get exported.

There is no custom-trained model: handwriting recognition is performed by Gemini vision. The application does not install or call Tesseract, EasyOCR, PaddleOCR, or another OCR engine.

## Setup
```
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then fill it in
python run.py
```
Open http://127.0.0.1:8000.

`.env` (never commit it):
```
SECRET_KEY=...        # python -c "import secrets; print(secrets.token_hex(32))"
MONGO_URI=...         # optional: leave empty to use a local SQLite file for development
GEMINI_API_KEY=...    # required
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash-lite
GEMINI_TIMEOUT_SECONDS=45
GEMINI_RETRIES=1
GEMINI_RETRY_DELAY_SECONDS=1.5
COOKIE_SECURE=0       # set to 1 behind HTTPS
COOKIE_SAMESITE=lax   # use "none" (with COOKIE_SECURE=1) if embedded in a Hugging Face Space iframe
```

## API
| Method and path | Body | Returns |
|---|---|---|
| `POST /api/auth/signup` | JSON: name, email, username, password, accept_terms | 201, logs you in |
| `POST /api/auth/login` | JSON: username, password | 200, sets session cookie |
| `POST /api/auth/logout` | none | 200 |
| `GET /api/auth/me` | none | `{authenticated, user}` |
| `POST /api/extract` | multipart: `file` | `{text, engine, warnings}`; Gemini errors return HTTP 503 |
| `POST /api/export/pdf` | JSON: `{text}` | PDF file |
| `POST /api/export/pptx` | multipart: `file`, `text` | PowerPoint file |
| `GET /api/health` | none | storage backend and whether Gemini is configured |

All `/api/extract` and `/api/export/*` routes need a logged-in session.

## Security notes
- Passwords use salted PBKDF2-SHA256. Accounts from the old app (unsalted SHA-256) still log in and are upgraded automatically on their next login.
- Login is limited to 5 failed attempts per 10 minutes for each IP and username.
- Sessions are signed, HTTP-only cookies. Uploads are checked as real images and limited to 10 MB.

## Testing
```
pip install -r requirements-dev.txt
python -m pytest tests -q
```
Covers Gemini-only model fallback, no-OCR failure behaviour, Unicode PDF export, PowerPoint structure, error-rate functions, password hashing (including legacy hashes), and the API (signup, login, rate limit, extract, both exports, rejection of non-images).

## Docker / Hugging Face Spaces
`Dockerfile` installs no OCR system packages and serves on port 7860. Set the variables above as Space secrets.

## Measuring accuracy
Put handwritten images and typed ground truth side by side (`note1.jpg` + `note1.txt`) in a folder, then run:
```
python backend/evaluate.py test_data --engine gemini
python backend/evaluate.py test_data
```
It reports mean character error rate (CER) and word error rate (WER).

| Engine | Images | CER | WER |
|---|---|---|---|
| Gemini | fill in | fill in | fill in |

