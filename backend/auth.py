"""
Vynce Auth - JWT token creation/verification and password hashing.
"""

from datetime import datetime, timedelta
import logging
import httpx
import smtplib
from typing import Optional

import bcrypt
from email_validator import validate_email, EmailNotValidError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import config
from .database import get_db
from .models import User

logger = logging.getLogger(__name__)


# Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, username: str) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + timedelta(hours=config.JWT_EXPIRY_HOURS)
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency - extracts and validates the current user from JWT."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising for unauthenticated requests."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def verify_email_existence(email: str) -> tuple[bool, str]:
    """
    Validates email syntax for all signups.
    Uses AbstractAPI for deep deliverability validation if configured.
    Returns (is_valid, error_message).
    """
    email = email.strip()
    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized
    except EmailNotValidError as e:
        return False, f"Email domain validation failed: {str(e)}"
    
    if config.EMAIL_VERIFICATION_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://emailvalidation.abstractapi.com/v1/",
                    params={"api_key": config.EMAIL_VERIFICATION_API_KEY, "email": email},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("deliverability") == "UNDELIVERABLE":
                        return False, "This email address does not exist."
                    if data.get("is_disposable_email", {}).get("value") is True:
                        return False, "Disposable emails are not allowed."
                else:
                    logger.error(f"Email validation API error: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to reach email validation API: {e}")
    else:
        logger.warning("EMAIL_VERIFICATION_API_KEY is not set. Deep verification skipped.")
            
    return True, ""


def send_verification_email(email: str, code: str):
    """
    Sends verification email if SMTP environment variables are configured.
    Otherwise, logs the code to the console.
    """
    import os
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_sender = os.getenv("SMTP_SENDER", smtp_user)

    subject = "Vynce Account Verification Code"
    body = f"Your Vynce verification code is: {code}\nThis code will expire in 10 minutes."
    message = f"Subject: {subject}\n\n{body}"

    # Print to logs for developer visibility
    logger.info("==================================================")
    logger.info(f"[EMAIL VERIFICATION CODE] FOR {email}: {code}")
    logger.info("==================================================")

    if smtp_host and smtp_port and smtp_user and smtp_password:
        try:
            port = int(smtp_port)
            if port == 465:
                server = smtplib.SMTP_SSL(smtp_host, port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, port, timeout=10)
                server.ehlo()
                server.starttls()
                server.ehlo()
            
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_sender, [email], message)
            server.quit()
            logger.info(f"Verification email successfully sent to {email}")
        except Exception as e:
            logger.error(f"Failed to send verification email to {email}: {e}")


