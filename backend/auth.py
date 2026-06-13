"""JWT authentication helpers for NetWatch API."""

import jwt
import datetime
import secrets
from functools import wraps
from flask import request, jsonify

SECRET_KEY = "netwatch-secret-key-change-in-production"


def generate_access_token(username, user_id, expires_in_minutes=60):
    """Generate a short-lived JWT access token."""
    payload = {
        "sub": username,
        "user_id": user_id,
        "type": "access",
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_in_minutes),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def generate_refresh_token():
    """Generate a long refresh token string (for storage in DB)."""
    return secrets.token_urlsafe(64)


def verify_token(token):
    """Decode and verify a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def require_auth(f):
    """Decorator to protect routes with JWT authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header"}), 401

        token = auth_header.split(" ", 1)[1]
        payload = verify_token(token)
        if not payload or payload.get("type") != "access":
            return jsonify({"error": "Invalid or expired token"}), 401

        return f(*args, **kwargs)
    return decorated
