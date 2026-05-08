# API diff logic + helpers + Redis caching + JWT authentication
from typing import Optional, Any, Callable
from functools import wraps
from datetime import datetime, timedelta
import json
import logging
import hashlib

# Redis imports
import redis
from redis.exceptions import RedisError

# JWT and security imports
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================

# JWT Configuration
SECRET_KEY = "your-secret-key-change-in-production"  # TODO: Move to environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Redis Configuration
REDIS_HOST = "localhost"  # TODO: Move to environment variable
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None  # TODO: Set in production
REDIS_DECODE_RESPONSES = True
CACHE_DEFAULT_TTL = 300  # 5 minutes default cache TTL

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer security scheme
security = HTTPBearer()


# ============================================================
# Redis Cache Manager
# ============================================================

class RedisCache:
    """
    Redis cache manager for caching API responses and data.
    
    Provides methods for get, set, delete, and cache invalidation
    with automatic serialization/deserialization and error handling.
    """
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self):
        """Establish connection to Redis server."""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=REDIS_DECODE_RESPONSES,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            self.redis_client = None
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {str(e)}")
            self.redis_client = None
    
    def is_available(self) -> bool:
        """Check if Redis is available."""
        if not self.redis_client:
            return False
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache by key.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value (deserialized from JSON) or None if not found
        """
        if not self.is_available():
            logger.warning("Redis not available, cache get failed")
            return None
        
        try:
            value = self.redis_client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to deserialize cached value for key {key}: {str(e)}")
            # Delete corrupted cache entry
            self.delete(key)
            return None
        except RedisError as e:
            logger.error(f"Redis error getting key {key}: {str(e)}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = CACHE_DEFAULT_TTL) -> bool:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache (will be serialized to JSON)
            ttl: Time to live in seconds (default: 300)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            logger.warning("Redis not available, cache set failed")
            return False
        
        try:
            serialized_value = json.dumps(value, default=str)  # default=str handles datetime
            self.redis_client.setex(key, ttl, serialized_value)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except (TypeError, json.JSONEncodeError) as e:
            logger.error(f"Failed to serialize value for key {key}: {str(e)}")
            return False
        except RedisError as e:
            logger.error(f"Redis error setting key {key}: {str(e)}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete key from cache.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            self.redis_client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return True
        except RedisError as e:
            logger.error(f"Redis error deleting key {key}: {str(e)}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (e.g., "analytics:*")
            
        Returns:
            Number of keys deleted
        """
        if not self.is_available():
            return 0
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"Cache DELETE PATTERN: {pattern} ({deleted} keys)")
                return deleted
            return 0
        except RedisError as e:
            logger.error(f"Redis error deleting pattern {pattern}: {str(e)}")
            return 0
    
    def clear_all(self) -> bool:
        """
        Clear all keys in current database.
        
        WARNING: Use with caution in production!
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            self.redis_client.flushdb()
            logger.warning("Cache CLEARED: All keys deleted from current database")
            return True
        except RedisError as e:
            logger.error(f"Redis error clearing database: {str(e)}")
            return False
    
    def get_ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for a key.
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds, None if key doesn't exist or error
        """
        if not self.is_available():
            return None
        
        try:
            ttl = self.redis_client.ttl(key)
            return ttl if ttl > 0 else None
        except RedisError as e:
            logger.error(f"Redis error getting TTL for key {key}: {str(e)}")
            return None


# Global cache instance
cache = RedisCache()


def generate_cache_key(*args, **kwargs) -> str:
    """
    Generate a cache key from arguments.
    
    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        MD5 hash of the arguments as cache key
    """
    # Create a string representation of all arguments
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    key_string = ":".join(key_parts)
    
    # Generate MD5 hash
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    return key_hash


def cached(prefix: str = "cache", ttl: int = CACHE_DEFAULT_TTL):
    """
    Decorator for caching function results in Redis.
    
    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        
    Usage:
        @cached(prefix="analytics:summary", ttl=600)
        def get_summary(api_id: int):
            return expensive_computation(api_id)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{prefix}:{generate_cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def invalidate_cache_pattern(pattern: str):
    """
    Invalidate all cache entries matching a pattern.
    
    Args:
        pattern: Pattern to match (e.g., "analytics:*")
    """
    cache.delete_pattern(pattern)


# ============================================================
# JWT Authentication
# ============================================================

class JWTAuth:
    """
    JWT authentication manager for securing API endpoints.
    
    Provides token generation, validation, and user authentication.
    """
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password
            
        Returns:
            True if password matches, False otherwise
        """
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Hash a password.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password
        """
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token.
        
        Args:
            data: Data to encode in token (e.g., {"sub": "user_id"})
            expires_delta: Token expiration time
            
        Returns:
            Encoded JWT token
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "iat": datetime.utcnow()})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """
        Create a JWT refresh token with longer expiration.
        
        Args:
            data: Data to encode in token
            
        Returns:
            Encoded JWT refresh token
        """
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode = data.copy()
        to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})
        
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def decode_token(token: str) -> dict:
        """
        Decode and validate a JWT token.
        
        Args:
            token: JWT token to decode
            
        Returns:
            Decoded token payload
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            logger.error(f"JWT decode error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )


# Global JWT auth instance
jwt_auth = JWTAuth()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get current authenticated user from JWT token.
    
    Args:
        credentials: HTTP Authorization credentials
        
    Returns:
        User data from token payload
        
    Raises:
        HTTPException: If authentication fails
        
    Usage:
        @router.get("/protected")
        async def protected_route(current_user: dict = Depends(get_current_user)):
            return {"user": current_user}
    """
    token = credentials.credentials
    payload = jwt_auth.decode_token(token)
    
    # Validate token type (should not be refresh token)
    if payload.get("type") == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Use access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "user_id": user_id,
        "username": payload.get("username"),
        "email": payload.get("email"),
        "roles": payload.get("roles", []),
        "permissions": payload.get("permissions", [])
    }


async def get_current_user_optional(
    authorization: Optional[str] = Header(None)
) -> Optional[dict]:
    """
    Optional authentication dependency - doesn't raise error if no token.
    
    Args:
        authorization: Authorization header
        
    Returns:
        User data if authenticated, None otherwise
        
    Usage:
        @router.get("/public-or-private")
        async def route(current_user: Optional[dict] = Depends(get_current_user_optional)):
            if current_user:
                # Authenticated user
                pass
            else:
                # Anonymous user
                pass
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    try:
        token = authorization.split(" ")[1]
        payload = jwt_auth.decode_token(token)
        
        user_id = payload.get("sub")
        if user_id:
            return {
                "user_id": user_id,
                "username": payload.get("username"),
                "email": payload.get("email"),
                "roles": payload.get("roles", []),
                "permissions": payload.get("permissions", [])
            }
    except Exception:
        pass
    
    return None


def require_permission(permission: str):
    """
    Dependency factory to require specific permission.
    
    Args:
        permission: Required permission name
        
    Returns:
        Dependency function
        
    Usage:
        @router.post("/admin")
        async def admin_route(current_user: dict = Depends(require_permission("admin:write"))):
            return {"message": "Admin access granted"}
    """
    async def permission_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_permissions = current_user.get("permissions", [])
        if permission not in user_permissions and "admin:all" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required permission: {permission}"
            )
        return current_user
    return permission_checker


def require_role(role: str):
    """
    Dependency factory to require specific role.
    
    Args:
        role: Required role name
        
    Returns:
        Dependency function
        
    Usage:
        @router.get("/admin")
        async def admin_route(current_user: dict = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_roles = current_user.get("roles", [])
        if role not in user_roles and "superadmin" not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {role}"
            )
        return current_user
    return role_checker


# ============================================================
# Helper Functions
# ============================================================

def create_token_response(user_data: dict) -> dict:
    """
    Create a complete token response with access and refresh tokens.
    
    Args:
        user_data: User data to encode in tokens
        
    Returns:
        Dictionary with access_token, refresh_token, and token_type
    """
    access_token = jwt_auth.create_access_token(data=user_data)
    refresh_token = jwt_auth.create_refresh_token(data=user_data)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    }


def hash_password(password: str) -> str:
    """
    Convenience function to hash a password.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password
    """
    return jwt_auth.get_password_hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Convenience function to verify a password.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password
        
    Returns:
        True if password matches, False otherwise
    """
    return jwt_auth.verify_password(plain_password, hashed_password)
