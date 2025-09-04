from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.models.user import User, RefreshToken
from app.core.security import get_password_hash, verify_password
from app.core.exceptions import NotFoundException, InvalidDataException
from typing import Optional, List
from datetime import datetime

async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
    """Get user by ID"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User", user_id)
    return user

async def get_user_by_email(db: AsyncSession, email: str) -> User:
    """Get user by email"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User", email)
    return user

async def get_users(
    db: AsyncSession, 
    school_id: Optional[int] = None,
    role: Optional[str] = None,
    skip: int = 0, 
    limit: int = 100
) -> List[User]:
    """Get users with optional filters"""
    query = select(User)
    
    if school_id is not None:
        query = query.where(User.school_id == school_id)
    
    if role is not None:
        query = query.where(User.role == role)
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def create_user(db: AsyncSession, user_data: dict) -> User:
    """Create a new user"""
    if 'password' in user_data:
        user_data['hashed_password'] = get_password_hash(user_data['password'])
        del user_data['password']
    
    if 'hashed_password' not in user_data:
        raise InvalidDataException("Password is required to create a user.")
    
    db_user = User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user(db: AsyncSession, user_id: int, user_data: dict) -> User:
    """Update a user"""
    if 'password' in user_data:
        user_data['hashed_password'] = get_password_hash(user_data['password'])
        del user_data['password']
    
    result = await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(**user_data)
        .returning(User)
    )
    await db.commit()
    updated_user = result.scalar_one_or_none()
    if not updated_user:
        raise NotFoundException("User", user_id)
    return updated_user

async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """Delete a user"""
    # First, fetch the user object to trigger cascade delete
    user_to_delete = await get_user_by_id(db, user_id)
    
    if not user_to_delete:
        raise NotFoundException("User", user_id)
        
    await db.delete(user_to_delete)
    await db.commit()
    return True

async def get_refresh_token(db: AsyncSession, token: str) -> RefreshToken:
    """Get refresh token by token string"""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == token)
    )
    refresh_token = result.scalar_one_or_none()
    if not refresh_token:
        raise NotFoundException("RefreshToken", token)
    return refresh_token

async def create_refresh_token(db: AsyncSession, user_id: int, token: str, expires_at: datetime) -> RefreshToken:
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

async def revoke_refresh_token(db: AsyncSession, token_id: int) -> RefreshToken:
    """Revoke a refresh token"""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == token_id)
    )
    token = result.scalar_one_or_none()
    
    if not token:
        raise NotFoundException("RefreshToken", token_id)
    
    token.revoked = True
    await db.commit()
    await db.refresh(token)
    
    return token

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """Authenticate a user with email and password"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(password, user.hashed_password):
        raise NotFoundException("User", email)
    
    return user

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