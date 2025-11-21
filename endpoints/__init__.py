from fastapi import APIRouter

from .agent_endpoints.resume_extraction import router as resume_router
from .crud_endpoints.org_user_auth import router as org_user_auth_router
from .crud_endpoints.candidate_auth import router as candidate_auth_router

router = APIRouter()

# Include sub-routers
router.include_router(resume_router)
router.include_router(org_user_auth_router)
router.include_router(candidate_auth_router)

# Add your API endpoints here
# Example:
# @router.get("/example")
# async def example_endpoint():
#     return {"message": "This is an example endpoint"}
