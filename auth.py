"""Password hashing + simple cookie sessions (no JWT, no external service)."""
import hashlib, hmac, os, secrets
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
from models import User

# session token -> user id (kept in memory; restarting the server logs everyone out)
SESSIONS = {}


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$")
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(check, digest)


def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    SESSIONS[token] = user_id
    return token


def user_from_request(request: Request, db: Session):
    """Returns the logged-in user or None."""
    user_id = SESSIONS.get(request.cookies.get("session"))
    return db.query(User).get(user_id) if user_id else None


def current_user(request: Request, db: Session = Depends(get_db)):
    user = user_from_request(request, db)
    if not user:
        raise HTTPException(401, "Please login first")
    return user


def admin_user(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin access only")
    return user
