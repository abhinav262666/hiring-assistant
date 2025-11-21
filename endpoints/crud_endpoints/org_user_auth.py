import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from models import Organization, OrgUser
from utils.auth import AuthService, get_current_org_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/org-user", tags=["org-user-auth"])


# Pydantic models for request/response
class OrgUserRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    org_id: str


class OrgUserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/register", response_model=AuthResponse)
async def register_org_user(request: OrgUserRegisterRequest):
    """
    Register a new organization user.

    - Validates organization exists
    - Checks email uniqueness within organization
    - Hashes password and creates user
    - Returns JWT token
    """
    try:
        # Validate organization exists
        org = Organization.objects(id=request.org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check if user already exists in this organization
        existing_user = OrgUser.objects(org=org, email=request.email).first()
        if existing_user:
            raise HTTPException(
                status_code=400, detail="User already exists in this organization"
            )

        # Create new user
        hashed_password = AuthService.get_password_hash(request.password)

        user = OrgUser(
            org=org,
            email=request.email,
            password_hash=hashed_password,
            name=request.name,
        )
        user.save()

        # Create access token
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "org_id": str(user.org.id),
        }
        access_token = AuthService.create_access_token(token_data, user_type="org_user")

        logger.info(f"OrgUser registered: {user.email} (org: {org.name})")

        return AuthResponse(
            access_token=access_token,
            user={
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "org_id": str(user.org.id),
                "org_name": org.name,
                "user_type": "org_user",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering org user: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to register user")


@router.post("/login", response_model=AuthResponse)
async def login_org_user(request: OrgUserLoginRequest):
    """
    Login organization user.

    - Validates credentials
    - Returns JWT token with user info
    """
    try:
        # Find user by email (across all orgs - email is globally unique per org)
        # Note: In a real app, you might want org-specific login or global email uniqueness
        user = OrgUser.objects(email=request.email).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Verify password
        if not AuthService.verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create access token
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "org_id": str(user.org.id),
        }
        access_token = AuthService.create_access_token(token_data, user_type="org_user")

        logger.info(f"OrgUser logged in: {user.email}")

        return AuthResponse(
            access_token=access_token,
            user={
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "org_id": str(user.org.id),
                "org_name": user.org.name,
                "user_type": "org_user",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging in org user: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.get("/me")
async def get_current_org_user_info(current_user: dict = Depends(get_current_org_user)):
    """
    Get current authenticated org user information.
    """
    try:
        user = OrgUser.objects(id=current_user["user_id"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "org_id": str(user.org.id),
            "org_name": user.org.name,
            "user_type": "org_user",
            "created_at": user.created_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting org user info: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get user information")
