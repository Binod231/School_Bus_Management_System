from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, RefreshToken
from app.core.security import verify_password, get_password_hash
from datetime import datetime, timedelta
from app.core.jwt import decode_access_token
from app.services.user import get_user_by_id

async def authenticate_user(db: AsyncSession, email: str, password: str):
    """Authenticate a user with email and password"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(password, user.hashed_password):
        return None
    
    return user


async def create_refresh_token(db: AsyncSession, user_id: int, token: str, expires_at: datetime):
    """Create a new refresh token"""
    db_token = RefreshToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at
    )
    db.add(db_token)
    await db.commit()
    await db.refresh(db_token)
    return db_token


async def get_refresh_token(db: AsyncSession, token: str):
    """Get a refresh token by token string"""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == token)
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token_id: int):
    """Revoke a refresh token"""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == token_id)
    )
    token = result.scalar_one_or_none()
    
    if token:
        token.revoked = True
        await db.commit()
    
    return token


async def revoke_all_user_tokens(db: AsyncSession, user_id: int):
    """Revoke all refresh tokens for a user"""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id)
    )
    tokens = result.scalars().all()
    
    for token in tokens:
        token.revoked = True
    
    await db.commit()
    return tokens

