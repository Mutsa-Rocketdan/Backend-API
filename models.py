import uuid
from datetime import datetime, date as date_obj
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Float, JSON, Enum as SQLEnum, BigInteger, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from database import Base

class LearningLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    nickname = Column(String, nullable=True)
    role = Column(SQLEnum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    lectures = relationship("Lecture", back_populates="user")
    quiz_results = relationship("QuizResult", back_populates="user")
    tasks = relationship("AITask", back_populates="user")

class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    learning_level = Column(SQLEnum(LearningLevel), default=LearningLevel.BEGINNER)
    interests = Column(JSONB, nullable=True)  # List of interest tags
    fcm_token = Column(String, nullable=True)

    user = relationship("User", back_populates="profile")

class Lecture(Base):
    __tablename__ = "lectures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    title = Column(String, index=True)
    content = Column(Text)
    
    week = Column(Integer, nullable=True)
    subject = Column(String, nullable=True)
    instructor = Column(String, nullable=True)
    session = Column(String, nullable=True)
    date = Column(Date, nullable=True)
    learning_goal = Column(Text, nullable=True)
    has_code_quiz = Column(Boolean, default=True, server_default="true")

    # pgvector 도입 전까지는 JSONB에 임베딩 저장 가능
    vector_embedding = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="lectures")
    concepts = relationship("Concept", back_populates="lecture")
    quizzes = relationship("Quiz", back_populates="lecture")
    guide = relationship("Guide", back_populates="lecture", uselist=False)

class Concept(Base):
    __tablename__ = "concepts"

    id = Column(BigInteger, primary_key=True, index=True)
    lecture_id = Column(UUID(as_uuid=True), ForeignKey("lectures.id"))
    concept_name = Column(String, index=True)
    description = Column(Text)
    mastery_score = Column(Float, default=0.0)

    lecture = relationship("Lecture", back_populates="concepts")

class AITask(Base):
    __tablename__ = "ai_tasks"

    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    lecture_id = Column(UUID(as_uuid=True), ForeignKey("lectures.id"), nullable=True)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=True)
    
    type = Column(String)  # quiz_generation, guide_generation, etc.
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    progress = Column(Integer, default=0)
    result_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="tasks")
    lecture = relationship("Lecture", backref="associated_tasks")
    quiz = relationship("Quiz", backref="associated_tasks")

class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lecture_id = Column(UUID(as_uuid=True), ForeignKey("lectures.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    title = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lecture = relationship("Lecture", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz")
    results = relationship("QuizResult", back_populates="quiz")

class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(BigInteger, primary_key=True, index=True)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"))
    question_text = Column(Text)
    options = Column(JSONB)
    correct_answer = Column(String)
    explanation = Column(Text)
    quiz_type = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)

    quiz = relationship("Quiz", back_populates="questions")

class QuizResult(Base):
    __tablename__ = "quiz_results"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"))
    score = Column(Integer)
    user_answers = Column(JSONB)  # List of answers submitted
    ai_feedback = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="quiz_results")
    quiz = relationship("Quiz", back_populates="results")

class Guide(Base):
    __tablename__ = "guides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lecture_id = Column(UUID(as_uuid=True), ForeignKey("lectures.id"), unique=True)
    summary = Column(Text)
    key_summaries = Column(JSONB)     # 핵심 요약 리스트
    review_checklist = Column(JSONB)  # 체크리스트 리스트
    concept_map = Column(JSONB)       # 개념 맵 데이터 (노드/엣지 등)
    created_at = Column(DateTime, default=datetime.utcnow)

    lecture = relationship("Lecture", back_populates="guide")
