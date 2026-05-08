# Authentication routes - Login, Register, Token Management
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import timedelta

from app.utils import (
    jwt_auth,
    create_token_response,
    hash_password,
    verify_password,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

# Create router for authentication endpoints
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={
        401: {"description": "Authentication failed"},
        422: {"description": "Validation error"}
    }
)

security = HTTPBearer()


# ============================================================
# Request/Response Schemas
# ============================================================

class UserRegister(BaseModel):
    """Schema for user registration"""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, max_length=100, description="Password (min 8 characters)")
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "SecurePass123!",
                "full_name": "John Doe"
            }
        }


class UserLogin(BaseModel):
    """Schema for user login"""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "SecurePass123!"
            }
        }


class TokenResponse(BaseModel):
    """Schema for token response"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str = Field(..., description="Refresh token")


class PasswordChange(BaseModel):
    """Schema for password change"""
    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password (min 8 characters)")


# ============================================================
# Mock User Database (Replace with real database in production)
# ============================================================

# In-memory user storage for demonstration
# TODO: Replace with actual database model and queries
MOCK_USERS = {
    "admin": {
        "user_id": "1",
        "username": "admin",
        "email": "admin@example.com",
        "password_hash": hash_password("admin123"),  # Default password: admin123
        "full_name": "Administrator",
        "roles": ["admin", "user"],
        "permissions": ["admin:all", "api:read", "api:write", "analytics:read", "analytics:write"]
    },
    "demo": {
        "user_id": "2",
        "username": "demo",
        "email": "demo@example.com",
        "password_hash": hash_password("demo123"),  # Default password: demo123
        "full_name": "Demo User",
        "roles": ["user"],
        "permissions": ["api:read", "analytics:read"]
    }
}


# ============================================================
# Authentication Endpoints
# ============================================================

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account and receive authentication tokens",
    responses={
        201: {"description": "User successfully registered"},
        400: {"description": "Username or email already exists"},
        422: {"description": "Validation error"}
    }
)
async def register(user_data: UserRegister):
    """
    Register a new user account.
    
    **Request Body:**
    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Secure password (minimum 8 characters)
    - **full_name**: Optional full name
    
    **Returns:**
    - Access token and refresh token for immediate authentication
    
    **Errors:**
    - 400: If username or email already exists
    - 422: If validation fails
    
    **Note:** This is a demo implementation. In production:
    - Store users in a real database
    - Implement email verification
    - Add rate limiting
    - Enforce strong password policies
    """
    # Check if username exists
    if user_data.username in MOCK_USERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Check if email exists
    for user in MOCK_USERS.values():
        if user["email"] == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Create new user
    user_id = str(len(MOCK_USERS) + 1)
    MOCK_USERS[user_data.username] = {
        "user_id": user_id,
        "username": user_data.username,
        "email": user_data.email,
        "password_hash": hash_password(user_data.password),
        "full_name": user_data.full_name or user_data.username,
        "roles": ["user"],
        "permissions": ["api:read", "analytics:read"]
    }
    
    # Generate tokens
    token_data = {
        "sub": user_id,
        "username": user_data.username,
        "email": user_data.email,
        "roles": ["user"],
        "permissions": ["api:read", "analytics:read"]
    }
    
    return create_token_response(token_data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login",
    description="Authenticate user and receive tokens",
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"}
    }
)
async def login(credentials: UserLogin):
    """
    Authenticate user with username/email and password.
    
    **Request Body:**
    - **username**: Username or email address
    - **password**: User password
    
    **Returns:**
    - Access token (valid for 30 minutes)
    - Refresh token (valid for 7 days)
    
    **Default Accounts:**
    - Admin: username=`admin`, password=`admin123`
    - Demo: username=`demo`, password=`demo123`
    
    **Errors:**
    - 401: If credentials are invalid
    
    **Security Features:**
    - Password hashing with bcrypt
    - JWT tokens with expiration
    - Secure token generation
    """
    # Find user by username
    user = MOCK_USERS.get(credentials.username)
    
    # If not found by username, try email
    if not user:
        for u in MOCK_USERS.values():
            if u["email"] == credentials.username:
                user = u
                break
    
    # Verify user exists and password is correct
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate tokens
    token_data = {
        "sub": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "roles": user["roles"],
        "permissions": user["permissions"]
    }
    
    return create_token_response(token_data)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Get a new access token using a refresh token",
    responses={
        200: {"description": "Token refreshed successfully"},
        401: {"description": "Invalid or expired refresh token"}
    }
)
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh an expired access token using a valid refresh token.
    
    **Request Body:**
    - **refresh_token**: Valid refresh token
    
    **Returns:**
    - New access token and refresh token
    
    **Errors:**
    - 401: If refresh token is invalid or expired
    
    **Use Case:**
    - When access token expires (30 minutes)
    - Avoid requiring user to log in again
    - Refresh tokens are valid for 7 days
    """
    try:
        # Decode refresh token
        payload = jwt_auth.decode_token(request.refresh_token)
        
        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Generate new tokens with same payload
        user_id = payload.get("sub")
        token_data = {
            "sub": user_id,
            "username": payload.get("username"),
            "email": payload.get("email"),
            "roles": payload.get("roles", []),
            "permissions": payload.get("permissions", [])
        }
        
        return create_token_response(token_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/logout",
    summary="User logout",
    description="Logout user (client-side token deletion)",
    responses={
        200: {"description": "Logout successful"}
    }
)
async def logout():
    """
    Logout user.
    
    **Note:** Since JWT tokens are stateless, logout is handled client-side
    by deleting the stored tokens. The tokens will expire naturally.
    
    **For production:**
    - Implement token blacklist in Redis
    - Add token revocation endpoint
    - Clear refresh tokens from database
    
    **Returns:**
    - Success message
    """
    return {
        "message": "Logout successful",
        "detail": "Please delete tokens from client storage"
    }


@router.get(
    "/me",
    summary="Get current user info",
    description="Get information about the currently authenticated user"
)
async def get_current_user_info():
    """
    Get current authenticated user information.
    
    **Authentication Required:** Yes (Bearer token)
    
    **Returns:**
    - User ID, username, email, roles, and permissions
    
    **Note:** This endpoint requires authentication.
    In the actual implementation, it would use the get_current_user dependency.
    """
    return {
        "message": "This endpoint requires authentication",
        "detail": "Use the get_current_user dependency to protect routes",
        "example": "current_user: dict = Depends(get_current_user)"
    }


# ============================================================
# Password Management
# ============================================================

@router.post(
    "/change-password",
    summary="Change password",
    description="Change user password (requires authentication)",
    responses={
        200: {"description": "Password changed successfully"},
        401: {"description": "Invalid current password"}
    }
)
async def change_password(password_data: PasswordChange):
    """
    Change user password.
    
    **Authentication Required:** Yes
    
    **Request Body:**
    - **old_password**: Current password
    - **new_password**: New password (min 8 characters)
    
    **Returns:**
    - Success message
    
    **Errors:**
    - 401: If current password is incorrect
    
    **Note:** In production, use get_current_user dependency to get user context
    """
    return {
        "message": "Password change functionality",
        "detail": "Implement with database and get_current_user dependency"
    }


# ============================================================
# Token Verification
# ============================================================

@router.post(
    "/verify-token",
    summary="Verify token validity",
    description="Check if a token is valid and not expired",
    responses={
        200: {"description": "Token is valid"},
        401: {"description": "Token is invalid or expired"}
    }
)
async def verify_token(token: str):
    """
    Verify if a JWT token is valid.
    
    **Query Parameters:**
    - **token**: JWT token to verify
    
    **Returns:**
    - Token payload if valid
    
    **Errors:**
    - 401: If token is invalid or expired
    
    **Use Case:**
    - Verify token before making API calls
    - Check token expiration
    - Validate token structure
    """
    try:
        payload = jwt_auth.decode_token(token)
        return {
            "valid": True,
            "payload": payload,
            "expires_at": payload.get("exp")
        }
    except HTTPException as e:
        return {
            "valid": False,
            "error": e.detail
        }
