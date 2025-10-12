from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.services.user import get_user_by_id
from sqlalchemy.orm import selectinload
from app.models.user import UserRole, User
from app.models.student import Guardian

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_token(token)
    if not payload:
        raise credentials_exception
    
    user_id: int = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    user = await get_user_by_id(db, user_id=int(user_id))
    if user is None or not user.is_active:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user = Depends(get_current_user),
):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_superadmin(
    current_user = Depends(get_current_active_user),
):
    if current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_current_admin(
    current_user = Depends(get_current_active_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_current_driver(
    current_user = Depends(get_current_active_user),
):
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_current_guardian(
    current_user = Depends(get_current_active_user),
):
    if current_user.role != UserRole.GUARDIAN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


def verify_school_resource_access(resource):
    """Dependency to check if a resource belongs to the current user's school."""
    async def _verify_school_resource_access(current_user: User = Depends(get_current_active_user)):
        if current_user.role == UserRole.SUPERADMIN:
            return
        
        if resource.school_id != current_user.school_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Resource does not belong to your school"
            )
    
    return _verify_school_resource_access

async def get_current_user_from_token(token: str, db: AsyncSession = Depends(get_db)):
    """
    Decodes a JWT token and retrieves the user. If the user is a guardian,
    it eagerly loads all necessary student relationships to prevent async errors.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_token(token)
    if not payload:
        raise credentials_exception
    
    user_id: int = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    # ✅ THE FINAL FIX: This query now eagerly loads the entire chain of relationships
    # needed for authorization: User -> Guardian -> GuardianStudent -> Student.
    query = (
        select(User)
        .options(
            selectinload(User.guardian_students)  # Load the Guardian profile(s)
            .selectinload(Guardian.students)    # Then, load the student associations within each Guardian
        )
        .filter(User.id == int(user_id))
    )
    result = await db.execute(query)
    user = result.scalars().first()
    
    if user is None or not user.is_active:
        raise credentials_exception
    
    return user

async def get_user_for_websocket(token: str, db: AsyncSession) -> Optional[User]:
    """
    Decodes a JWT token and retrieves a user from the database without using Depends().
    This makes it safe to use within WebSocket endpoints. Returns None if auth fails.
    """
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        return None
    
    user_id = int(payload.get("sub"))
    user = await get_user_by_id(db, user_id=user_id)
    
    if user and user.role == UserRole.GUARDIAN:
        # Eagerly load relationships to prevent async "lazy load" errors in the WebSocket context
        result = await db.execute(
            select(User)
            .options(selectinload(User.guardian_students).selectinload(Guardian.students))
            .filter(User.id == user.id)
        )
        user = result.scalars().first()

    return user if user and user.is_active else None