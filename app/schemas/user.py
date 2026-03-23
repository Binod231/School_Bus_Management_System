from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime, date
from app.models.user import UserRole # Import the enum from the models

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role: UserRole # Use the imported enum

class UserCreate(UserBase):
    password: str
    school_id: Optional[int] = None
    license_number: Optional[str] = None
    license_expiry: Optional[date] = None

    @validator('password')
    def password_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    school_id: Optional[int] = None
    license_number: Optional[str] = None
    license_expiry: Optional[date] = None
    assigned_students: Optional[List[int]] = []
    skipped_students: Optional[List[int]] = []

class UserResponse(UserBase):
    id: int
    school_id: Optional[int] = None
    is_active: bool
    license_number: Optional[str] = None
    license_expiry: Optional[date] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenData(BaseModel):
    sub: Optional[int] = None
    role: Optional[str] = None

class RefreshTokenCreate(BaseModel):
    token: str
    expires_at: datetime

class RefreshTokenResponse(BaseModel):
    id: int
    user_id: int
    token: str
    expires_at: datetime
    revoked: bool
    created_at: datetime

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @validator('new_password')
    def password_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v