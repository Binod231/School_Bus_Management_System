from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta, datetime
import uuid
import json
from app.db.session import get_db
from app.core.config import settings
from app.core.cache import redis_client
from app.core.security import create_access_token, create_refresh_token, verify_password, get_password_hash
from app.services.user import create_refresh_token as create_db_refresh_token, authenticate_user, get_user_by_id, get_refresh_token, revoke_refresh_token, get_user_by_email, revoke_all_user_tokens
from app.services.trip import authorize_trip_access
from app.schemas.user import Token, UserCreate, UserResponse, PasswordResetRequest, PasswordResetConfirm
from app.models.user import UserRole, User
from app.core.exceptions import NotFoundException
from app.core.jwt import get_current_active_user
from app.utils.upload import save_profile_picture, delete_old_profile_picture

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    try:
        user = await authenticate_user(db, email=form_data.username, password=form_data.password)
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    refresh_token_expires = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=refresh_token_expires
    )
    
    await create_db_refresh_token(db, user_id=user.id, token=refresh_token, expires_at=datetime.utcnow() + refresh_token_expires)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        await get_user_by_email(db, email=user_data.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    except NotFoundException:
        pass
    
    if user_data.role == UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create superadmin account through this endpoint"
        )
    
    from app.services.user import create_user
    user = await create_user(db, user_data=user_data.dict())
    
    return user


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    from app.core.security import decode_token
    
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    try:
        db_token = await get_refresh_token(db, token=refresh_token)
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    if db_token.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    try:
        user = await get_user_by_id(db, user_id=int(user_id))
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    new_refresh_token_expires = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        expires_delta=new_refresh_token_expires
    )
    
    await revoke_refresh_token(db, db_token.id)
    await create_db_refresh_token(db, user_id=user.id, token=new_refresh_token, expires_at=datetime.utcnow() + new_refresh_token_expires)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }


@router.post("/forgot-password")
async def forgot_password(
    request_data: PasswordResetRequest, # CHANGE THIS LINE
    db: AsyncSession = Depends(get_db)
):
    from app.utils.email import send_password_reset_email

    try:
        # And CHANGE THIS LINE to access the email from the request data
        user = await get_user_by_email(db, email=request_data.email) 

        reset_token_expires = timedelta(minutes=30)
        reset_token = create_access_token(
            data={"sub": str(user.id), "purpose": "password_reset"},
            expires_delta=reset_token_expires
        )

        await send_password_reset_email(user.email, reset_token)
    except NotFoundException:
        pass

    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    # CHANGE THIS: Use the Pydantic schema for the request body
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    from app.core.security import decode_token
    from app.services.user import update_user
    
    # CHANGE THIS: Access data from the schema object
    payload = decode_token(reset_data.token)
    if not payload or payload.get("purpose") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )
    
    user_id = payload.get("sub")
    try:
        user = await get_user_by_id(db, user_id=int(user_id))
    except NotFoundException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found or inactive"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found or inactive"
        )
    
    # CHANGE THIS: Access data from the schema object
    hashed_password = get_password_hash(reset_data.new_password)
    await update_user(db, user_id=user.id, user_data={"hashed_password": hashed_password})
    
    return {"message": "Password has been reset successfully"}

@router.post(
    "/logout",
    summary="Logout user and revoke all refresh tokens",
    description="Revokes all refresh tokens for the current user, forcing them to log in again on all devices."
)
async def logout(
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    await revoke_all_user_tokens(db, user_id=current_user.id)
    return {"message": "Logged out successfully"}

@router.get("/users/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """
    Get current logged-in user.
    """
    return current_user


@router.post("/users/me/profile-picture", response_model=UserResponse)
async def upload_user_profile_picture(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads or updates the current authenticated user's profile picture.
    """
    delete_old_profile_picture(current_user.profile_picture_url)
    url = await save_profile_picture(file)
    current_user.profile_picture_url = url
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.delete("/users/me/profile-picture", response_model=UserResponse)
async def delete_user_profile_picture(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Removes the current authenticated user's profile picture.
    """
    delete_old_profile_picture(current_user.profile_picture_url)
    current_user.profile_picture_url = None
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post(
    "/ws-ticket",
    summary="Generate single-use WebSocket ticket",
    description="Issues a short-lived (60s) single-use ticket for connecting to live trip WebSocket feeds."
)
async def generate_websocket_ticket(
    trip_id: int = Query(..., description="ID of the trip to subscribe to"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify user is authorized for this trip
    is_authorized = await authorize_trip_access(db, current_user, trip_id)
    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to subscribe to live updates for this trip."
        )

    ticket = str(uuid.uuid4())
    ticket_data = json.dumps({
        "user_id": current_user.id,
        "trip_id": trip_id,
        "role": current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    })
    # Store in Redis for 60 seconds
    await redis_client.set(f"ws_ticket:{ticket}", ticket_data, ex=60)

    return {
        "ticket": ticket,
        "expires_in": 60,
        "trip_id": trip_id
    }



