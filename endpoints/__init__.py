from fastapi import APIRouter

from .agent_endpoints.resume_extraction import router as resume_router

router = APIRouter()

# Include sub-routers
router.include_router(resume_router)

# Add your API endpoints here
# Example:
# @router.get("/example")
# async def example_endpoint():
#     return {"message": "This is an example endpoint"}
