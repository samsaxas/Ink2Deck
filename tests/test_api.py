"""End-to-end API tests. Needs: pip install -r requirements-dev.txt"""
import hashlib
import io
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

# Configure before the app is imported.
os.environ["USERS_DB"] = os.path.join(tempfile.mkdtemp(), "users.db")
os.environ["SECRET_KEY"] = "test-secret"
os.environ.pop("MONGO_URI", None)
os.environ.pop("GEMINI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import db  # noqa: E402
from main import app  # noqa: E402

# FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT = r"C:\Windows\Fonts\arial.ttf"


@pytest.fixture()
def client():
    return TestClient(app, follow_redirects=False)


def png_bytes(text="Meeting notes for Monday"):
    img = Image.new("RGB", (1000, 160), "white")
    ImageDraw.Draw(img).text((20, 40), text, fill="black", font=ImageFont.truetype(FONT, 48))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def signup(client, username="alice", password="s3cret-pass", **overrides):
    body = {
        "name": "Alice",
        "email": f"{username}@example.com",
        "username": username,
        "password": password,
        "accept_terms": True,
    }
    body.update(overrides)
    return client.post("/api/auth/signup", json=body)


def test_pages_and_redirects(client):
    assert client.get("/").status_code == 200
    assert client.get("/login").status_code == 200
    assert client.get("/app").headers["location"] == "/login"
    assert client.get("/static/css/style.css").status_code == 200


def test_signup_validation_messages(client):
    assert signup(client, "bob1", password="short").status_code == 400
    assert signup(client, "bob2", accept_terms=False).status_code == 400
    assert signup(client, "bob3", email="not-an-email").status_code == 400
    assert signup(client, "x").status_code == 400


def test_signup_logs_in_then_logout(client):
    assert signup(client, "carol").status_code == 201
    assert client.get("/api/auth/me").json()["user"]["username"] == "carol"
    assert client.get("/app").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_duplicate_username_rejected(client):
    assert signup(client, "dave").status_code == 201
    assert signup(client, "dave", password="another-pass").status_code == 409


def test_login_wrong_password_and_rate_limit(client):
    signup(client, "erin")
    client.post("/api/auth/logout")
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "erin", "password": "bad"})
        assert r.status_code == 401
    assert client.post("/api/auth/login", json={"username": "erin", "password": "s3cret-pass"}).status_code == 429


def test_legacy_sha256_account_logs_in_and_is_upgraded(client):
    legacy = hashlib.sha256(b"old-pass").hexdigest()
    db.get_store().create_user("Old User", "old@example.com", "olduser", legacy)
    r = client.post("/api/auth/login", json={"username": "olduser", "password": "old-pass"})
    assert r.status_code == 200
    assert db.get_store().find_by_username("olduser")["password"].startswith("pbkdf2_sha256$")


def test_api_requires_login(client):
    assert client.post("/api/extract", files={"file": ("a.png", png_bytes(), "image/png")}).status_code == 401
    assert client.post("/api/export/pdf", json={"text": "hi"}).status_code == 401


def test_extract_and_export(client):
    signup(client, "frank")
    r = client.post("/api/extract", files={"file": ("a.png", png_bytes(), "image/png")})
    assert r.status_code == 200
    data = r.json()
    # assert data["engine"] == "tesseract" and "Monday" in data["text"]
    assert data["engine"] == "gemini"
    assert "Monday" in data["text"]

    pdf = client.post("/api/export/pdf", json={"text": "x\u00b2 \u2265 5"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    pptx = client.post(
        "/api/export/pptx",
        files={"file": ("a.png", png_bytes(), "image/png")},
        data={"text": "First\n\nSecond"},
    )
    assert pptx.status_code == 200 and pptx.content[:2] == b"PK"


def test_rejects_non_images_and_empty_text(client):
    signup(client, "gina")
    bad = client.post("/api/extract", files={"file": ("a.png", b"not an image", "image/png")})
    assert bad.status_code == 400
    assert client.post("/api/export/pdf", json={"text": "   "}).status_code == 400
