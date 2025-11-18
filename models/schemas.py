from datetime import datetime
from random import choices
from mongoengine import (
    DynamicDocument, EmbeddedDocument, ReferenceField,
    StringField, EmailField, DateTimeField, ListField, FloatField, DictField, URLField,
    EmbeddedDocumentField, CASCADE, NULLIFY
)
 
from models.qdrant_mixin import QdrantMixin
 

 
class ScreeningResult(EmbeddedDocument):
    verdict = StringField(choices=("pass", "fail", "manual_review"), default="manual_review")
    score = FloatField()
    matched_skills = ListField(StringField())
    explanation = StringField()
 
 
class StageUpdate(EmbeddedDocument):
    by = ReferenceField('OrgUser', reverse_delete_rule=NULLIFY)
    at = DateTimeField(default=datetime.utcnow)
    note = StringField()
 
 
class SkillMatch(EmbeddedDocument):
    skill = StringField(required=True)
    match_score = FloatField(required=True)
 
 
 
class Organization(DynamicDocument, QdrantMixin):
    name = StringField(required=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
 

 
class OrgUser(DynamicDocument, QdrantMixin):
    org = ReferenceField(Organization, required=True, reverse_delete_rule=CASCADE)
    email = EmailField(required=True)
    password_hash = StringField(required=True)  
    name = StringField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
 
    meta = {
        "collection": "org_users",
        "indexes": [
            {"fields": ["org", "email"], "unique": True}
        ]
    }
 
 
class Candidate(DynamicDocument, QdrantMixin):
    org = ReferenceField(Organization, required=True, reverse_delete_rule=CASCADE)
    email = EmailField()
    name = StringField()
    phone = StringField()
    resume_link = URLField()  
    resume_ocr_content = StringField()  
    location = StringField()
    current_company = StringField()
    experience_years = FloatField()
    skills = ListField(StringField())
    status = StringField(choices=("active", "archived", "deleted"), default="active")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
 
    meta = {
        "collection": "candidates",
        "indexes": [
            {"fields": ["org", "email"], "unique": True, "sparse": True},
            {"fields": ["org", "skills"]},
            {"fields": ["org", "experience_years"]},
        ]
    }
 
 
class JobListing(DynamicDocument, QdrantMixin):
    org = ReferenceField(Organization, required=True, reverse_delete_rule=CASCADE)
    title = StringField(required=True)
    description = StringField()
    location = StringField()
    employment_type = StringField(choices=["full-time, part-time, contract"], default="full-time")  
    salary_range = StringField() 
    experience_required_min = FloatField()
    experience_required_max = FloatField()
    required_skills = ListField(StringField())
    nice_to_have = ListField(StringField())
    created_by = ReferenceField(OrgUser, reverse_delete_rule=NULLIFY)
    status = StringField(choices=("open", "closed", "paused"), default="open")
    published_at = DateTimeField()
    metadata = DictField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
 
    meta = {
        "collection": "job_listings",
        "indexes": [
            {"fields": ["org", "status"]},
            {"fields": ["org", "required_skills"]},
            {"fields": ["org", "published_at"]},
            {"fields": ["$title", "$description"], "default_language": "english", "weights": {"title": 10, "description": 2}}
        ]
    }
 
 
class Application(DynamicDocument, QdrantMixin):
    org = ReferenceField(Organization, required=True, reverse_delete_rule=CASCADE)
    job = ReferenceField(JobListing, required=True, reverse_delete_rule=CASCADE)
    candidate = ReferenceField(Candidate, required=True, reverse_delete_rule=CASCADE)
    source = StringField(default="candidate_portal")  # "referral", "api", etc.
    applied_at = DateTimeField(default=datetime.utcnow)
    status = StringField(choices=("screening", "interviewed", "offered", "hired", "rejected"), default="screening")
    screening_result = EmbeddedDocumentField(ScreeningResult)
    current_stage_updates = ListField(EmbeddedDocumentField(StageUpdate))
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
 
    meta = {
        "collection": "applications",
        "indexes": [
            {"fields": ["org", "job"]},
            {"fields": ["org", "candidate"]},
            {"fields": ["org", "status"]},
        ]
    }
 
 
class CandidateListingMapping(DynamicDocument, QdrantMixin):
    org = ReferenceField(Organization, required=True, reverse_delete_rule=CASCADE)
    candidate = ReferenceField(Candidate, required=True, reverse_delete_rule=CASCADE)
    job = ReferenceField(JobListing, required=True, reverse_delete_rule=CASCADE)
    skill_matches = ListField(EmbeddedDocumentField(SkillMatch))
    experience_match_score = FloatField()
    location_match_score = FloatField()
    interview_score = FloatField()
   