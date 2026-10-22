"""User storage.

- If MONGO_URI is set, users live in MongoDB, in the same `Ink2Deck.users`
  collection the Streamlit app used, so existing accounts keep working.
- If MONGO_URI is not set, a local SQLite file is used so the app runs with
  zero setup during development.
"""
import os
import sqlite3
import threading
from pathlib import Path


class DuplicateUser(Exception):
    """Username or email is already registered."""


class StoreUnavailable(Exception):
    """The database cannot be reached."""


class MongoStore:
    name = "mongodb"

    def __init__(self, uri: str):
        # import certifi
        from pymongo import MongoClient

        # MongoClient connects lazily, so creating it never blocks start-up.
        self._client = MongoClient(
            uri,
            # tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=3000,
        )
        self._users = self._client["Ink2Deck"]["users"]

    def _guard(self, fn):
        from pymongo.errors import PyMongoError

        try:
            return fn()
        except PyMongoError as exc:
            raise StoreUnavailable(str(exc)) from exc

    def find_by_username(self, username):
        return self._guard(lambda: self._users.find_one({"username": username}))

    def exists(self, username, email):
        query = {"$or": [{"username": username}, {"email": email}]}
        return self._guard(lambda: self._users.find_one(query) is not None)

    def create_user(self, name, email, username, password_hash):
        self._guard(
            lambda: self._users.insert_one(
                {
                    "name": name,
                    "email": email,
                    "username": username,
                    "password": password_hash,
                }
            )
        )

    def set_password_hash(self, username, password_hash):
        self._guard(
            lambda: self._users.update_one(
                {"username": username}, {"$set": {"password": password_hash}}
            )
        )


class SQLiteStore:
    name = "sqlite"

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute(
                """CREATE TABLE IF NOT EXISTS users (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       name TEXT NOT NULL,
                       email TEXT NOT NULL,
                       username TEXT NOT NULL,
                       password TEXT NOT NULL
                   )"""
            )
            self._db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"
            )
            self._db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)"
            )
            self._db.commit()

    def find_by_username(self, username):
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        return dict(row) if row else None

    def exists(self, username, email):
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM users WHERE username = ? OR email = ?", (username, email)
            ).fetchone()
        return row is not None

    def create_user(self, name, email, username, password_hash):
        try:
            with self._lock:
                self._db.execute(
                    "INSERT INTO users (name, email, username, password) VALUES (?, ?, ?, ?)",
                    (name, email, username, password_hash),
                )
                self._db.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateUser() from exc

    def set_password_hash(self, username, password_hash):
        with self._lock:
            self._db.execute(
                "UPDATE users SET password = ? WHERE username = ?",
                (password_hash, username),
            )
            self._db.commit()


_store = None


def get_store():
    """Create the store on first use and reuse it afterwards."""
    global _store
    if _store is None:
        uri = os.getenv("MONGO_URI", "").strip().strip('"').strip("'")
        if uri:
            _store = MongoStore(uri)
        else:
            default = Path(__file__).resolve().parent / "data" / "users.db"
            _store = SQLiteStore(Path(os.getenv("USERS_DB", str(default))))
    return _store


def reset_store():
    """Forget the cached store (used by tests)."""
    global _store
    _store = None
