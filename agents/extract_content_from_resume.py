from baml_client import b
from models import Candidate


async def extract_content_from_resume(resume: str) -> Candidate:
    resume_content = await b.ExtractResume(resume)
    return resume_content
