from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging

from models import Candidate, Organization
from utils.auth import AuthService, get_current_candidate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/candidate", tags=["candidate-auth"])


# Pydantic models for request/response
class CandidateRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    org_id: str


class CandidateLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class SetPasswordRequest(BaseModel):
    password: str


@router.post("/register", response_model=AuthResponse)
async def register_candidate(request: CandidateRegisterRequest):
    """
    Register a new candidate.

    Note: In practice, candidates are usually created through resume upload.
    This endpoint allows candidates to set passwords for existing candidate records.
    """
    try:
        # Validate organization exists
        org = Organization.objects(id=request.org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check if candidate already exists in this organization
        existing_candidate = Candidate.objects(org=org, email=request.email).first()
        if existing_candidate:
            # If candidate exists but no password set, allow setting password
            if hasattr(existing_candidate, 'password_hash') and existing_candidate.password_hash:
                raise HTTPException(status_code=400, detail="Candidate already registered")

            # Set password for existing candidate
            existing_candidate.password_hash = AuthService.get_password_hash(request.password)
            if request.name:
                existing_candidate.name = request.name
            existing_candidate.save()
            candidate = existing_candidate
        else:
            # Create new candidate (though typically done via resume upload)
            candidate = Candidate(
                org=org,
                email=request.email,
                name=request.name,
                password_hash=AuthService.get_password_hash(request.password),
                status="active"
            )
            candidate.save()

        # Create access token
        token_data = {
            "sub": str(candidate.id),
            "email": candidate.email,
            "name": candidate.name,
            "org_id": str(candidate.org.id)
        }
        access_token = AuthService.create_access_token(token_data, user_type="candidate")

        logger.info(f"Candidate registered: {candidate.email} (org: {org.name})")

        return AuthResponse(
            access_token=access_token,
            user={
                "id": str(candidate.id),
                "email": candidate.email,
                "name": candidate.name,
                "org_id": str(candidate.org.id),
                "org_name": org.name,
                "user_type": "candidate",
                "experience_years": candidate.experience_years,
                "skills": candidate.skills
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering candidate: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to register candidate")


@router.post("/login", response_model=AuthResponse)
async def login_candidate(request: CandidateLoginRequest):
    """
    Login candidate.

    - Validates credentials against existing candidate records
    """
    try:
        # Find candidate by email (across all orgs)
        candidate = Candidate.objects(email=request.email).first()

        if not candidate:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Check if candidate has a password set
        if not hasattr(candidate, 'password_hash') or not candidate.password_hash:
            raise HTTPException(
                status_code=401,
                detail="Password not set. Please register first or contact support."
            )

        # Verify password
        if not AuthService.verify_password(request.password, candidate.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create access token
        token_data = {
            "sub": str(candidate.id),
            "email": candidate.email,
            "name": candidate.name,
            "org_id": str(candidate.org.id)
        }
        access_token = AuthService.create_access_token(token_data, user_type="candidate")

        logger.info(f"Candidate logged in: {candidate.email}")

        return AuthResponse(
            access_token=access_token,
            user={
                "id": str(candidate.id),
                "email": candidate.email,
                "name": candidate.name,
                "org_id": str(candidate.org.id),
                "org_name": candidate.org.name,
                "user_type": "candidate",
                "experience_years": candidate.experience_years,
                "skills": candidate.skills,
                "current_company": candidate.current_company,
                "location": candidate.location
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging in candidate: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.get("/me")
async def get_current_candidate_info(current_user: dict = Depends(get_current_candidate)):
    """
    Get current authenticated candidate information.
    """
    try:
        candidate = Candidate.objects(id=current_user["user_id"]).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        return {
            "id": str(candidate.id),
            "email": candidate.email,
            "name": candidate.name,
            "phone": candidate.phone,
            "org_id": str(candidate.org.id),
            "org_name": candidate.org.name,
            "user_type": "candidate",
            "experience_years": candidate.experience_years,
            "skills": candidate.skills,
            "current_company": candidate.current_company,
            "location": candidate.location,
            "status": candidate.status,
            "created_at": candidate.created_at.isoformat(),
            "resume_url": candidate.resume_link
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting candidate info: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get candidate information")


@router.post("/set-password")
async def set_candidate_password(
    request: SetPasswordRequest,
    current_user: dict = Depends(get_current_candidate)
):
    """
    Allow authenticated candidate to set/update their password.
    """
    try:
        candidate = Candidate.objects(id=current_user["user_id"]).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate.password_hash = AuthService.get_password_hash(request.password)
        candidate.save()

        logger.info(f"Password set for candidate: {candidate.email}")

        return {"message": "Password set successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting candidate password: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to set password")
