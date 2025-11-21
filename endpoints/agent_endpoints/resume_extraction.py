from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from agents.extract_content_from_resume import extract_content_from_resume
from models import Candidate, Organization
from settings import senv
from utils.ocr_service import OCRService
from utils.upload_to_s3 import get_s3_service

logger = senv.backend_logger

router = APIRouter(prefix="/resume", tags=["resume-extraction"])


@router.post("/extract")
async def extract_resume_content(
    file: UploadFile = File(...),
    org_id: str = Header(..., alias="X-Organization-ID"),
):
    """
    Extract candidate information from resume file.

    Args:
        file: Resume file (PDF, TXT, DOC, etc.)
        org_id: Organization ID from header

    Returns:
        Created candidate information
    """
    try:
        # Validate organization exists
        org = Organization.objects(id=org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Validate file type using OCR service
        if not OCRService.is_supported_filetype(file.filename):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Supported formats: PDF, TXT, MD",
            )

        # Read file content
        file_content = await file.read()

        # Extract text using OCR service
        try:
            resume_text = OCRService.extract_text_from_file(file_content, file.filename)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to extract text from file: {str(e)}"
            )

        # Upload original file to S3
        try:
            s3_service = get_s3_service()
            resume_url = s3_service.upload_file(
                file_content=file_content,
                filename=file.filename,
                content_type=file.content_type,
            )
        except Exception as e:
            logger.warning(
                f"Failed to upload resume to S3: {str(e)}. Continuing without S3 upload."
            )
            resume_url = None

        # Extract content using BAML agent
        candidate_data = await extract_content_from_resume(resume_text)

        # Create candidate with additional required fields
        candidate = Candidate(
            org=org,
            email=candidate_data.email,
            name=candidate_data.name,
            phone=getattr(candidate_data, "phone", None),
            resume_link=resume_url,  # S3 URL if upload succeeded, None otherwise
            resume_ocr_content=resume_text,  # Store the extracted text for embeddings
            location=getattr(candidate_data, "location", None),
            current_company=getattr(candidate_data, "current_company", None),
            experience_years=candidate_data.experience_years,
            skills=candidate_data.skills,
            status="active",
        )

        # Save to database (this will also sync to Qdrant via signals)
        candidate.save()

        logger.info(f"Created candidate {candidate.id} for org {org_id}")

        # Return candidate data
        response_data = {
            "id": str(candidate.id),
            "name": candidate.name,
            "email": candidate.email,
            "phone": candidate.phone,
            "experience_years": candidate.experience_years,
            "skills": candidate.skills,
            "location": candidate.location,
            "current_company": candidate.current_company,
            "status": candidate.status,
            "created_at": candidate.created_at.isoformat(),
            "org_id": str(candidate.org.id),
        }

        if candidate.resume_link:
            response_data["resume_url"] = candidate.resume_link

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting resume content: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process resume: {str(e)}"
        )
