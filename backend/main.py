"""Ink2Deck backend (FastAPI).

Serves the website from ../frontend and exposes a small JSON API under /api.
Run from the project root with:  python run.py
"""
import io
import logging
import os
import re
import secrets
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv  # noqa: E402

# Load .env before importing ocr_utils, which reads GEMINI_MODEL at import time.
load_dotenv(ROOT_DIR / ".env")

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from db import DuplicateUser, StoreUnavailable, get_store  # noqa: E402
from ocr_utils import (  # noqa: E402
    create_pdf,
    create_ppt_with_text_and_image,
    extract_text,
    GeminiExtractionError,
    to_rgb,
)
from security import DUMMY_HASH, hash_password, verify_password  # noqa: E402

log = logging.getLogger("ink2deck")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 50_000
MAX_IMAGE_SIDE = 2560
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = 60_000_000

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    log.warning("SECRET_KEY is not set. Using a random key, so logins reset on every restart.")

app = FastAPI(title="Ink2Deck", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="ink2deck_session",
    max_age=60 * 60 * 24 * 7,
    same_site=os.getenv("COOKIE_SAMESITE", "lax"),
    https_only=os.getenv("COOKIE_SECURE", "0") == "1",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' blob: data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self' https://huggingface.co https://*.hf.space"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------- helpers

def current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    return user


def store():
    try:
        return get_store()
    except Exception as exc:  # bad MONGO_URI, unwritable SQLite path, etc.
        log.exception("Could not open user storage")
        raise HTTPException(status_code=503, detail="The account database is unavailable.") from exc


def storage_call(fn, *args):
    try:
        return fn(*args)
    except StoreUnavailable as exc:
        log.error("Database unavailable: %s", exc)
        raise HTTPException(
            status_code=503, detail="The account database is unavailable. Try again shortly."
        ) from exc


_FAILED_LOGINS = defaultdict(deque)
_WINDOW_SECONDS = 600
_MAX_FAILURES = 5


def _login_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}|{username.lower()}"


def _too_many_failures(key: str) -> bool:
    attempts = _FAILED_LOGINS[key]
    cutoff = time.time() - _WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return len(attempts) >= _MAX_FAILURES


def read_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That image is larger than 10 MB. Use a smaller photo.")
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    return data


def open_image(data: bytes) -> Image.Image:
    """Decode an upload into an upright RGB image of a sensible size."""
    try:
        image = Image.open(io.BytesIO(data))
        image_format = image.format
        image.load()
    except Exception:
        raise HTTPException(status_code=400, detail="That file is not a readable image. Use a JPG, PNG or WebP photo.")
    if image_format not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use a JPG, PNG or WebP photo.")
    try:
        image = ImageOps.exif_transpose(image)  # phone photos carry a rotation flag
    except Exception:
        pass
    image = to_rgb(image)
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    return image


def clean_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="There is no text to export.")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=413, detail="The text is too long to export.")
    return text


# ----------------------------------------------------------------- models

class SignupBody(BaseModel):
    name: str = ""
    email: str = ""
    username: str = ""
    password: str = ""
    accept_terms: bool = False


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""


class TextBody(BaseModel):
    text: str = ""


# -------------------------------------------------------------------- API

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "storage": "mongodb" if os.getenv("MONGO_URI", "").strip() else "sqlite",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.get("/api/auth/me")
def me(request: Request):
    user = request.session.get("user")
    return {"authenticated": bool(user), "user": user}


@app.post("/api/auth/signup", status_code=201)
def signup(body: SignupBody, request: Request):
    name = body.name.strip()
    email = body.email.strip().lower()
    username = body.username.strip()

    if not all([name, email, username, body.password]):
        raise HTTPException(status_code=400, detail="Fill in all fields.")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="Name is too long.")
    if not EMAIL_RE.match(email) or len(email) > 120:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3 to 32 characters: letters, numbers, dot, dash or underscore.",
        )
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if len(body.password) > 128:
        raise HTTPException(status_code=400, detail="Password must be at most 128 characters.")
    if not body.accept_terms:
        raise HTTPException(status_code=400, detail="Accept the Terms and Conditions to create an account.")

    users = store()
    if storage_call(users.exists, username, email):
        raise HTTPException(status_code=409, detail="That username or email is already registered.")
    try:
        storage_call(users.create_user, name, email, username, hash_password(body.password))
    except DuplicateUser:
        raise HTTPException(status_code=409, detail="That username or email is already registered.")

    request.session["user"] = {"username": username, "name": name}
    return {"ok": True, "user": request.session["user"]}


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request):
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="Enter your username and password.")

    key = _login_key(request, username)
    if _too_many_failures(key):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Wait 10 minutes and try again.")

    users = store()
    record = storage_call(users.find_by_username, username)
    stored_hash = record.get("password", "") if record else DUMMY_HASH
    ok, needs_rehash = verify_password(body.password, stored_hash)

    if not record or not ok:
        _FAILED_LOGINS[key].append(time.time())
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    _FAILED_LOGINS.pop(key, None)
    if needs_rehash:
        storage_call(users.set_password_hash, username, hash_password(body.password))

    request.session.clear()
    request.session["user"] = {"username": username, "name": record.get("name") or username}
    return {"ok": True, "user": request.session["user"]}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.post("/api/extract")
def extract(file: UploadFile = File(...), user: dict = Depends(current_user)):
    image = open_image(read_upload(file))
    try:
        text, engine = extract_text(image)
    except GeminiExtractionError as exc:
        log.exception("Gemini-only extraction failed")
        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini is temporarily unavailable. No alternative OCR engine was used. "
                "Check your Gemini API key, quota, and configured fallback models, then retry."
            ),
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="No text detected. Try a clearer, well-lit photo with the writing filling the frame.",
        )
    return {"text": text, "engine": engine, "warnings": []}


@app.post("/api/export/pdf")
def export_pdf(body: TextBody, user: dict = Depends(current_user)):
    pdf_bytes = create_pdf(clean_text(body.text))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="extracted_content.pdf"'},
    )


@app.post("/api/export/pptx")
def export_pptx(
    file: UploadFile = File(...),
    text: str = Form(...),
    user: dict = Depends(current_user),
):
    image = open_image(read_upload(file))
    stream = create_ppt_with_text_and_image(clean_text(text), image)
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="whiteboard_presentation.pptx"'},
    )


# ------------------------------------------------------------------ pages

@app.get("/", include_in_schema=False)
def home_page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/app", status_code=303)
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/app", include_in_schema=False)
def workspace_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(FRONTEND_DIR / "app.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
