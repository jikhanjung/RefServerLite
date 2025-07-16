from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os

from .models import User

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

security = HTTPBearer(auto_error=False)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return username"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[User]:
    """Get current user from JWT token"""
    if not credentials:
        return None
    
    username = verify_token(credentials.credentials)
    if not username:
        return None
    
    try:
        user = User.get(User.username == username)
        return user
    except User.DoesNotExist:
        return None

def require_admin(current_user: User = Depends(get_current_user)):
    """Require admin user for endpoint access"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user

def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[User]:
    """Get current user without raising exception if not authenticated"""
    return get_current_user(credentials)

def check_session_auth(request: Request) -> Optional[User]:
    """Check session-based authentication for web interface"""
    username = request.session.get("username")
    if not username:
        return None
    
    try:
        user = User.get(User.username == username)
        return user
    except User.DoesNotExist:
        return None

def require_session_admin(request: Request):
    """Require admin session for web interface"""
    user = check_session_auth(request)
    if not user or not user.is_admin:
        from fastapi.responses import RedirectResponse
        # Redirect to login page instead of raising exception
        return RedirectResponse(url="/login", status_code=302)
    return user