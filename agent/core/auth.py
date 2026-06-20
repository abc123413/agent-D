"""
认证模块 - JWT + SQLite用户管理
"""

import os
import time
import sqlite3
from pathlib import Path
from typing import Optional

import jwt
import bcrypt
from pydantic import BaseModel
from fastapi import HTTPException, Depends, Request


JWT_SECRET = os.getenv("JWT_SECRET", "agent-platform-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "users.db"


class User(BaseModel):
    id: int
    username: str
    created_at: float


class LoginRequest(BaseModel):
    username: str
    password: str


def _get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def register_user(username: str, password: str) -> User:
    if len(username) < 2 or len(password) < 4:
        raise HTTPException(400, "用户名至少2位，密码至少4位")

    conn = _get_db()
    try:
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, time.time()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return User(id=row["id"], username=row["username"], created_at=row["created_at"])
    except sqlite3.IntegrityError:
        raise HTTPException(400, "用户名已存在")
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> User:
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            raise HTTPException(401, "用户名或密码错误")
        if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            raise HTTPException(401, "用户名或密码错误")
        return User(id=row["id"], username=row["username"], created_at=row["created_at"])
    finally:
        conn.close()


def create_token(user: User) -> str:
    payload = {
        "user_id": user.id,
        "username": user.username,
        "exp": time.time() + JWT_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("exp", 0) < time.time():
            raise HTTPException(401, "Token已过期")
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(401, "无效Token")


def get_current_user(request: Request) -> Optional[User]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = auth_header[7:]
    payload = verify_token(token)
    return User(id=payload["user_id"], username=payload["username"], created_at=0)
