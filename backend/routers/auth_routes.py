"""
Vynce Auth Routes — Register, Login, Profile endpoints.
"""

from datetime import datetime, timedelta
import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_access_token, get_current_user, hash_password, verify_password, verify_email_existence, send_verification_email
from ..database import get_db
from ..models import User
from ..schemas import TokenResponse, UserLogin, UserRegister, UserResponse, RegisterResponse, UserVerify

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    """Create a new user account."""
    # Verify email exists and is valid
    is_valid, err_msg = verify_email_existence(payload.email)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Check if username already exists
    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # Generate verification code
    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Create user (unverified)
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_verified=False,
        verification_code=code,
        verification_code_expires_at=expires_at,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Send / log verification code
    send_verification_email(user.email, code)

    import os
    smtp_host = os.getenv("SMTP_HOST")
    expose_code = not bool(smtp_host)

    return RegisterResponse(
        requires_verification=True,
        email=user.email,
        message="Verification code sent to your email",
        code=code if expose_code else None,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Log in with email and password."""
    # Search for user by email OR username
    result = await db.execute(
        select(User).where(
            (User.email == payload.email) | (User.username == payload.email)
        )
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check if email is verified
    if not user.is_verified:
        # Regenerate verification code
        code = f"{random.randint(100000, 999999)}"
        user.verification_code = code
        user.verification_code_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
        
        # Resend code
        send_verification_email(user.email, code)
        
        import os
        smtp_host = os.getenv("SMTP_HOST")
        expose_code = not bool(smtp_host)

        detail_payload = {
            "error": "verification_required",
            "email": user.email,
            "message": "Email not verified. A new verification code has been sent."
        }
        if expose_code:
            detail_payload["code"] = code

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail_payload
        )

    token = create_access_token(user.id, user.username)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/verify", response_model=TokenResponse)
async def verify(payload: UserVerify, db: AsyncSession = Depends(get_db)):
    """Verify a user's email with the 6-digit code."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.is_verified:
        # Already verified, generate token and login
        token = create_access_token(user.id, user.username)
        return TokenResponse(
            access_token=token,
            user=UserResponse.model_validate(user),
        )

    # Check code and expiration
    if user.verification_code != payload.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code",
        )

    if datetime.utcnow() > user.verification_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired",
        )

    # Mark as verified
    user.is_verified = True
    user.verification_code = None
    user.verification_code_expires_at = None
    await db.commit()
    await db.refresh(user)

    # Log in user
    token = create_access_token(user.id, user.username)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get the current authenticated user's profile."""
    return UserResponse.model_validate(user)
