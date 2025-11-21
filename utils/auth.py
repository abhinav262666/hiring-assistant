from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from settings import senv

logger = senv.backend_logger

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = senv.jwt_secret_key
ALGORITHM = senv.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = senv.jwt_access_token_expire_minutes

# Security scheme
security = HTTPBearer()


class AuthService:
    """Authentication service for handling JWT tokens and password operations."""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(
        data: Dict[str, Any], user_type: str, expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT access token.

        Args:
            data: Token payload data
            user_type: Type of user ("org_user" or "candidate")
            expires_delta: Optional custom expiration time

        Returns:
            JWT token string
        """
        to_encode = data.copy()

        # Add user type to distinguish tokens
        to_encode.update(
            {
                "user_type": user_type,
                "iat": datetime.utcnow(),
                "exp": datetime.utcnow()
                + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)),
            }
        )

        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid authentication token")

    @staticmethod
    def get_current_user(
        token: HTTPAuthorizationCredentials = Depends(security),
    ) -> Dict[str, Any]:
        """
        Dependency to get current authenticated user from JWT token.

        Returns:
            User data from token payload
        """
        payload = AuthService.verify_token(token.credentials)

        # Check if token has required fields
        user_id = payload.get("sub")
        user_type = payload.get("user_type")

        if not user_id or not user_type:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return {
            "user_id": user_id,
            "user_type": user_type,
            "org_id": payload.get("org_id"),
            **payload,
        }

    @staticmethod
    def get_current_org_user(
        token_data: Dict = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """
        Dependency to get current org user (ensures user_type is org_user).
        """
        if token_data.get("user_type") != "org_user":
            raise HTTPException(
                status_code=403, detail="Not authorized as organization user"
            )

        return token_data

    @staticmethod
    def get_current_candidate(
        token_data: Dict = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """
        Dependency to get current candidate (ensures user_type is candidate).
        """
        if token_data.get("user_type") != "candidate":
            raise HTTPException(status_code=403, detail="Not authorized as candidate")

        return token_data
