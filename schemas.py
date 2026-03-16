from pydantic import BaseModel, EmailStr
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from models import LearningLevel, TaskStatus

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    nickname: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Profile Schemas ---
class UserProfileBase(BaseModel):
    learning_level: LearningLevel = LearningLevel.BEGINNER
    interests: Optional[List[str]] = None
    fcm_token: Optional[str] = None

class UserProfileResponse(UserProfileBase):
    user_id: UUID

    class Config:
        from_attributes = True

# --- Task Schemas ---
class AITaskBase(BaseModel):
    type: str

class AITaskResponse(AITaskBase):
    task_id: UUID
    status: TaskStatus
    progress: int
    result_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# --- Lecture Schemas ---
class LectureBase(BaseModel):
    title: str
    content: str

class LectureCreate(LectureBase):
    pass

class LectureResponse(LectureBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# --- Concept Schemas ---
class ConceptBase(BaseModel):
    concept_name: str
    description: Optional[str] = None
    mastery_score: float = 0.0

class ConceptResponse(ConceptBase):
    id: int
    lecture_id: UUID

    class Config:
        from_attributes = True

class ConceptUpdate(BaseModel):
    mastery_score: float
