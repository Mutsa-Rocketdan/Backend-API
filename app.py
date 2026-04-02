from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import os
from dotenv import load_dotenv

import models, schemas, auth
from database import SessionLocal, get_db

import sentry_sdk
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
import secrets

load_dotenv()

# --- Phase 6: Sentry Monitoring ---
SENTRY_DSN = (os.getenv("SENTRY_DSN") or "").strip()
_SENTRY_DSN_IS_PLACEHOLDER = SENTRY_DSN.lower() in {"your_sentry_dsn_here", "none", "null"}
_SENTRY_DSN_HAS_VALID_SCHEME = SENTRY_DSN.startswith("http://") or SENTRY_DSN.startswith("https://")

# DSN이 없거나 placeholder/형식이 잘못되면 Sentry 초기화를 건너뛰어 앱 부팅 크래시를 방지한다.
if SENTRY_DSN and (not _SENTRY_DSN_IS_PLACEHOLDER) and _SENTRY_DSN_HAS_VALID_SCHEME:
    try:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            traces_sample_rate=1.0,
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            # We recommend adjusting this value in production.
            profiles_sample_rate=1.0,
        )
    except Exception:
        # Sentry 설정 오류로 서버가 죽지 않도록 방어적으로 스킵한다.
        pass

# --- Phase 7: Rate Limiting Setup ---
limiter = Limiter(key_func=get_remote_address)

# --- Phase 9: Database initialization managed by Alembic ---
# models.Base.metadata.create_all(bind=engine)

# Swagger/ReDoc을 커스텀 보호하기 위해 기본값은 비활성화
app = FastAPI(
    title="AI Quiz & Guide Backend",
    docs_url=None, 
    redoc_url=None
)

# --- Phase 7: CORS Setup ---
# 추후 프론트엔드 도메인이 확정되면 ["https://your-app.vercel.app"] 등으로 수정 필요
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limit 예외 처리 등록
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Phase 6: Prometheus Metrics ---
Instrumentator().instrument(app).expose(app)

# --- Phase 7: Basic Auth for Docs ---
security_basic = HTTPBasic()

def authenticate_docs(credentials: HTTPBasicCredentials = Depends(security_basic)):
    correct_username = os.getenv("DOCS_USERNAME", "admin")
    correct_password = os.getenv("DOCS_PASSWORD", "quiz-guide-secret")
    
    is_username_correct = secrets.compare_digest(credentials.username, correct_username)
    is_password_correct = secrets.compare_digest(credentials.password, correct_password)
    
    if not (is_username_correct and is_password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect docs credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- 보안 관련 의존성 함수 ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """현재 토큰을 가지고 있는 사용자가 누구인지 확인하는 보안 가드"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = auth.jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except auth.JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_admin(current_user: models.User = Depends(get_current_user)):
    """현재 사용자가 관리자(ADMIN) 권한을 가지고 있는지 확인합니다."""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have enough permissions to perform this action."
        )
    return current_user

# --- API 엔드포인트 ---

@app.get("/")
@limiter.limit("5/minute")
async def root(request: auth.Request): # slowapi requires 'request' argument
    return {"message": "AI Quiz & Guide Backend is running", "version": "v1.1.0 (v2 build)"}

# --- Protected Docs Endpoints ---
@app.get("/docs", include_in_schema=False)
async def get_protected_docs(credentials: HTTPBasicCredentials = Depends(authenticate_docs)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API Docs")

@app.get("/redoc", include_in_schema=False)
async def get_protected_redoc(credentials: HTTPBasicCredentials = Depends(authenticate_docs)):
    return get_redoc_html(openapi_url="/openapi.json", title="API Redoc")

@app.post("/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """새로운 사용자를 등록합니다 (회원가입)"""
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pwd = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        nickname=user.nickname
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.Token)
@limiter.limit("5/minute")
def login_for_access_token(
    request: auth.Request,
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    """사용자 확인 후 출입증(JWT 토큰)을 발급합니다 (로그인)"""
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    """내 출입증을 보여주고 내 정보를 확인합니다 (내 정보 조회)"""
    return current_user

# --- Phase 4: Lecture & Concept APIs ---

from fastapi import BackgroundTasks
import src.ai_service as ai_service

@app.post("/lectures", response_model=schemas.LectureResponse)
async def create_lecture(
    lecture: schemas.LectureCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin)
):
    """(관리자 전용) 새로운 강의 자료를 업로드하고 개념 추출을 시작합니다."""
    # 1. 강의 저장
    new_lecture = models.Lecture(
        user_id=current_admin.id,
        title=lecture.title,
        content=lecture.content,
        week=lecture.week,
        subject=lecture.subject,
        instructor=lecture.instructor,
        session=lecture.session,
        date=lecture.date,
        learning_goal=lecture.learning_goal,
        has_code_quiz=lecture.has_code_quiz,
    )
    db.add(new_lecture)
    db.flush() # ID를 미리 얻기 위해
    
    # 2. 작업(AITask) 생성
    new_task = models.AITask(
        user_id=current_admin.id,
        lecture_id=new_lecture.id, # 핵심: 강의와 작업을 명확히 연결
        type="concept_extraction",
        status=models.TaskStatus.PENDING,
        progress=0
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_lecture)
    db.refresh(new_task)
    
    # 3. 비동기 작업을 응답 객체에 연결 (스키마 반영)
    new_lecture.task_id = new_task.task_id
    
    # 4. 비동기로 개념 추출 작업 시작
    background_tasks.add_task(
        ai_service.run_concept_extraction, 
        new_lecture.id, 
        new_lecture.content, 
        new_task.task_id,
        SessionLocal()
    )

    # 5. 학습 가이드도 자동 생성
    guide_task = models.AITask(
        user_id=current_admin.id,
        lecture_id=new_lecture.id,
        type="guide_generation",
        status=models.TaskStatus.PENDING,
        progress=0,
    )
    db.add(guide_task)
    db.commit()
    db.refresh(guide_task)
    background_tasks.add_task(
        ai_service.run_guide_generation,
        new_lecture.id,
        new_lecture.content,
        guide_task.task_id,
        SessionLocal(),
    )
    
    return new_lecture

@app.get("/tasks/{task_id}", response_model=schemas.AITaskResponse)
def get_task_status(task_id: UUID, db: Session = Depends(get_db)):
    """현재 진행 중인 AI 작업의 상태와 진행률을 확인합니다."""
    task = db.query(models.AITask).filter(models.AITask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.get("/lectures", response_model=List[schemas.LectureResponse])
def get_lectures(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """내가 접근 가능한 활성 강의 자료 목록을 가져옵니다. (Soft Delete된 것은 제외)"""
    return db.query(models.Lecture).filter(
        models.Lecture.is_active == True # 활성 상태인 것만 조회
    ).all()

@app.get("/lectures/{lecture_id}", response_model=schemas.LectureResponse)
def get_lecture_by_id(
    lecture_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """특정 강의 상세를 조회합니다."""
    lecture = db.query(models.Lecture).filter(
        models.Lecture.id == lecture_id,
        models.Lecture.is_active == True,
    ).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    return lecture

@app.delete("/lectures/{lecture_id}")
def delete_lecture(
    lecture_id: UUID, 
    db: Session = Depends(get_db), 
    current_admin: models.User = Depends(get_current_admin)
):
    """(관리자 전용) 강의를 삭제(비활성화)합니다. 실제 데이터를 지우지 않고 소프트 삭제 처리합니다."""
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    
    lecture.is_active = False # Soft Delete 처리
    db.commit()
    return {"message": "Lecture successfully deactivated (Soft Delete)"}

@app.get("/lectures/{lecture_id}/concepts", response_model=List[schemas.ConceptResponse])
def get_lecture_concepts(
    lecture_id: UUID, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """특정 강의에서 추출된 지식(개념) 목록을 조회합니다."""
    lecture = db.query(models.Lecture).filter(
        models.Lecture.id == lecture_id, 
        models.Lecture.is_active == True # 활성 강의만 개념 조회 가능
    ).first()
    
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
        
    return db.query(models.Concept).filter(models.Concept.lecture_id == lecture_id).all()

# --- Phase 5: Quiz & QuizResult APIs ---

@app.post("/lectures/{lecture_id}/quizzes", response_model=schemas.QuizResponse)
def create_quiz(
    lecture_id: UUID,
    background_tasks: BackgroundTasks,
    options: Optional[schemas.QuizCreateOptions] = None,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin)
):
    """(관리자 전용) 특정 강의를 바탕으로 AI 퀴즈 생성을 시작합니다."""
    lecture = db.query(models.Lecture).filter(
        models.Lecture.id == lecture_id, 
        models.Lecture.is_active == True
    ).first()
    
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    opts = options or schemas.QuizCreateOptions()
    quiz_types = opts.quiz_types or []
    if quiz_types:
        # lecture.has_code_quiz 가 false면 code 선택을 제거
        if not lecture.has_code_quiz:
            quiz_types = [t for t in quiz_types if t != "code"]
        if not quiz_types:
            quiz_types = ["multiple_choice"]

    new_quiz = models.Quiz(
        lecture_id=lecture_id,
        user_id=current_admin.id,
        title=f"{lecture.title} 복습 퀴즈"
    )
    db.add(new_quiz)
    db.flush()

    new_task = models.AITask(
        user_id=current_admin.id,
        lecture_id=lecture_id,
        quiz_id=new_quiz.id,
        type="quiz_generation",
        status=models.TaskStatus.PENDING,
        progress=0
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_quiz)
    
    new_quiz.task_id = new_task.task_id

    background_tasks.add_task(
        ai_service.run_quiz_generation,
        new_quiz.id,
        lecture_id,
        lecture.content,
        new_task.task_id,
        SessionLocal(),
        quiz_type=opts.quiz_type,
        quiz_types=quiz_types or None,
        difficulty=opts.difficulty,
        count=opts.count,
    )

    return new_quiz

@app.get("/quizzes/{quiz_id}", response_model=schemas.QuizResponse)
def get_quiz(quiz_id: UUID, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """특정 퀴즈의 문항들을 포함하여 조회합니다."""
    quiz = db.query(models.Quiz).filter(
        models.Quiz.id == quiz_id, 
        models.Quiz.is_active == True # 활성 퀴즈만 조회 가능
    ).first()
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # 여기서 questions는 relationship에 의해 자동 로드됨
    return quiz

@app.post("/quizzes/{quiz_id}/results", response_model=schemas.QuizResultResponse)
def submit_quiz_result(
    quiz_id: UUID,
    result: schemas.QuizResultCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """퀴즈 풀이 결과를 저장합니다."""
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    new_result = models.QuizResult(
        user_id=current_user.id,
        quiz_id=quiz_id,
        score=result.score,
        user_answers=result.user_answers,
        ai_feedback=result.ai_feedback
    )
    db.add(new_result)
    db.commit()
    db.refresh(new_result)

    # 퀴즈 결과에 따라 해당 강의의 이해도(Concept.mastery_score)를 업데이트
    try:
        lecture_id = quiz.lecture_id
        concepts = db.query(models.Concept).filter(models.Concept.lecture_id == lecture_id).all()
        questions = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == quiz_id).order_by(models.QuizQuestion.id.asc()).all()

        def _norm(s: str) -> str:
            return (s or "").strip().casefold()

        # 개념별로 "해당 개념과 관련된 문항"을 문자열 매칭으로 추정
        # - concept_name이 question_text 또는 explanation에 포함되면 해당 개념 문항으로 간주
        stats: dict[int, dict[str, int]] = {c.id: {"seen": 0, "correct": 0} for c in concepts}
        for i, q in enumerate(questions):
            ua = result.user_answers[i] if i < len(result.user_answers) else ""
            ca = q.correct_answer or ""
            qtype = (q.quiz_type or ("multiple_choice" if (q.options and len(q.options) > 0) else "short_answer")).strip()

            if qtype in {"short_answer", "fill_blank", "code"}:
                is_correct = _norm(ua) == _norm(ca)
            else:
                # multiple_choice
                is_correct = (ua or "").strip() == ca.strip()

            hay = f"{q.question_text or ''}\n{q.explanation or ''}"
            matched_any = False
            for c in concepts:
                name = (c.concept_name or "").strip()
                if name and name in hay:
                    stats[c.id]["seen"] += 1
                    stats[c.id]["correct"] += 1 if is_correct else 0
                    matched_any = True

            # 어떤 개념에도 매칭되지 않으면 전체에 영향 주지 않음(균등 업데이트 방지)
            if not matched_any:
                continue

        # 개념별 업데이트: 해당 개념 문항의 정확도를 EMA로 반영
        alpha = 0.35
        for c in concepts:
            seen = stats[c.id]["seen"]
            if seen <= 0:
                continue
            acc = stats[c.id]["correct"] / seen  # 0~1
            old = float(c.mastery_score or 0.0)
            new = (1.0 - alpha) * old + alpha * float(acc)
            c.mastery_score = max(0.0, min(1.0, new))
        db.commit()
    except Exception:
        # 이해도 업데이트 실패가 결과 저장을 막지 않도록 방어
        try:
            db.rollback()
        except Exception:
            pass
    return new_result

@app.get("/quiz-results", response_model=List[schemas.QuizResultResponse])
def get_my_quiz_results(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """내가 수행한 모든 퀴즈 결과 내역을 가져옵니다."""
    return db.query(models.QuizResult).filter(models.QuizResult.user_id == current_user.id).all()

# --- Phase 6: Study Guide APIs ---

@app.post("/lectures/{lecture_id}/guides", response_model=schemas.AITaskResponse)
async def create_study_guide(
    lecture_id: UUID, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """특정 강의를 바탕으로 학습 가이드(요약, 체크리스트 등) 생성을 시작합니다."""
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    existing = db.query(models.Guide).filter(models.Guide.lecture_id == lecture_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Guide already exists for this lecture")

    new_task = models.AITask(
        user_id=current_user.id,
        lecture_id=lecture_id,
        type="guide_generation",
        status=models.TaskStatus.PENDING,
        progress=0
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    background_tasks.add_task(
        ai_service.run_guide_generation,
        lecture_id,
        lecture.content,
        new_task.task_id,
        SessionLocal()
    )

    return new_task

@app.get("/lectures/{lecture_id}/guides", response_model=schemas.GuideResponse)
def get_study_guide(lecture_id: UUID, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """특정 강의에 대한 학습 가이드를 조회합니다."""
    guide = db.query(models.Guide).filter(models.Guide.lecture_id == lecture_id).first()
    if not guide:
        raise HTTPException(status_code=404, detail="Study guide not found for this lecture")
    return guide
