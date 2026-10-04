from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import jwt
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "telegram_simulator.db"
UPLOAD_DIR = BASE_DIR / "uploads"
AVATAR_DIR = UPLOAD_DIR / "avatars"
MESSAGE_DIR = UPLOAD_DIR / "messages"

for folder in (UPLOAD_DIR, AVATAR_DIR, MESSAGE_DIR):
    folder.mkdir(exist_ok=True)

SECRET_KEY = os.getenv("JWT_SECRET", "telegram-simulator-dev-secret-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Telegram Simulator", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    conn = create_db_connection()
    try:
        yield conn
    finally:
        conn.close()


def create_tables() -> None:
    with create_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                avatar_url TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                media_type TEXT,
                media_url TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def ensure_default_channel() -> None:
    with create_db_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO channels (name, description, created_by, created_at) VALUES (?, ?, ?, ?)",
                ("general", "General discussion channel", 0, utc_now_iso()),
            )
            conn.commit()


@app.on_event("startup")
def startup() -> None:
    create_tables()
    ensure_default_channel()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html", media_type="text/html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc).timestamp() + (ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def serialize_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
        "created_at": row["created_at"],
    }


def serialize_channel(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def serialize_message(row: sqlite3.Row) -> dict:
    user = {
        "id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
    }
    return {
        "id": row["id"],
        "channel_id": row["channel_id"],
        "text": row["text"],
        "media_type": row["media_type"],
        "media_url": row["media_url"],
        "created_at": row["created_at"],
        "user": user,
    }


async def save_upload(file: UploadFile, target_dir: Path) -> str:
    filename = file.filename or f"upload-{uuid.uuid4().hex}"
    extension = Path(filename).suffix.lower() or ".bin"
    saved_name = f"{uuid.uuid4().hex}{extension}"
    saved_path = target_dir / saved_name
    data = await file.read()
    saved_path.write_bytes(data)
    return f"/uploads/{target_dir.name}/{saved_name}"


def get_current_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject")

    row = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return serialize_user(row)


@app.post("/api/register")
async def register_user(
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    avatar: Optional[UploadFile] = File(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    username = username.strip()
    display_name = display_name.strip()
    if not username or not display_name or not password:
        raise HTTPException(status_code=400, detail="Username, display name, and password are required")

    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    avatar_url = None
    if avatar and avatar.filename:
        avatar_url = await save_upload(avatar, AVATAR_DIR)

    password_hash = hash_password(password)
    created_at = utc_now_iso()
    cursor = db.execute(
        "INSERT INTO users (username, display_name, password_hash, avatar_url, created_at) VALUES (?, ?, ?, ?, ?)",
        (username, display_name, password_hash, avatar_url, created_at),
    )
    db.commit()

    user_id = cursor.lastrowid
    token = create_token(user_id)
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"token": token, "user": serialize_user(row)}


@app.post("/api/login")
def login_user(
    username: str = Form(...),
    password: str = Form(...),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    username = username.strip()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(row["id"])
    return {"token": token, "user": serialize_user(row)}


@app.get("/api/me")
def get_me(current_user: dict = Depends(get_current_user)) -> dict:
    return {"user": current_user}


@app.get("/api/channels")
def list_channels(db: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = db.execute("SELECT * FROM channels ORDER BY created_at ASC").fetchall()
    return [serialize_channel(row) for row in rows]


@app.post("/api/channels")
def create_channel(
    name: str = Form(...),
    description: str = Form(""),
    current_user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    name = name.strip()
    description = description.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Channel name is required")

    cursor = db.execute(
        "INSERT INTO channels (name, description, created_by, created_at) VALUES (?, ?, ?, ?)",
        (name, description, current_user["id"], utc_now_iso()),
    )
    db.commit()
    channel_id = cursor.lastrowid
    row = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    return serialize_channel(row)


@app.get("/api/channels/{channel_id}/messages")
def list_messages(
    channel_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    _ = current_user
    rows = db.execute(
        """
        SELECT m.*, u.username, u.display_name, u.avatar_url
        FROM messages m
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.channel_id = ?
        ORDER BY m.created_at ASC
        """,
        (channel_id,),
    ).fetchall()
    return [serialize_message(row) for row in rows]


@app.post("/api/channels/{channel_id}/messages")
async def send_message(
    channel_id: int,
    text: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    current_user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    text = (text or "").strip()
    if not text and not file:
        raise HTTPException(status_code=400, detail="Message is empty")

    channel = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    media_url = None
    media_type = None
    if file and file.filename:
        media_url = await save_upload(file, MESSAGE_DIR)
        content_type = (file.content_type or "").lower()
        if content_type.startswith("image/"):
            media_type = "image"
        elif content_type.startswith("video/"):
            media_type = "video"
        elif content_type.startswith("audio/"):
            media_type = "audio"
        else:
            media_type = "file"

    created_at = utc_now_iso()
    cursor = db.execute(
        "INSERT INTO messages (channel_id, user_id, text, media_type, media_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (channel_id, current_user["id"], text, media_type, media_url, created_at),
    )
    db.commit()

    row = db.execute(
        """
        SELECT m.*, u.username, u.display_name, u.avatar_url
        FROM messages m
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return serialize_message(row)
