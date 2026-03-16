from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import os
from dotenv import load_dotenv

import models, schemas, auth
from database import engine, SessionLocal, get_db

load_dotenv()

# DB 테이블 생성 (Alembic을 썼지만, 혹시 모를 상황 대비)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Quiz & Guide Backend")

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

# --- API 엔드포인트 ---

@app.get("/")
async def root():
    return {"message": "AI Quiz & Guide Backend is running", "version": "1.0.0"}

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
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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
    current_user: models.User = Depends(get_current_user)
):
    """새로운 강의 자료를 업로드하고 개념 추출을 시작합니다."""
    # 1. 강의 저장
    new_lecture = models.Lecture(
        user_id=current_user.id,
        title=lecture.title,
        content=lecture.content
    )
    db.add(new_lecture)
    db.flush() # ID를 미리 얻기 위해
    
    # 2. 작업(AITask) 생성
    new_task = models.AITask(
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
    
    # 응답 헤더에 작업 ID를 추가하여 앱이 추적할 수 있게 함
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
    """내가 업로드한 모든 강의 자료 목록을 가져옵니다."""
    return db.query(models.Lecture).filter(models.Lecture.user_id == current_user.id).all()

@app.get("/lectures/{lecture_id}/concepts", response_model=List[schemas.ConceptResponse])
def get_lecture_concepts(
    lecture_id: UUID, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """특정 강의에서 추출된 지식(개념) 목록을 조회합니다."""
    lecture = db.query(models.Lecture).filter(
        models.Lecture.id == lecture_id, 
        models.Lecture.user_id == current_user.id
    ).first()
    
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
        
    return db.query(models.Concept).filter(models.Concept.lecture_id == lecture_id).all()

# --- Phase 5: Quiz & QuizResult APIs ---

@app.post("/lectures/{lecture_id}/quizzes", response_model=schemas.QuizResponse)
def create_quiz(
    lecture_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """특정 강의를 바탕으로 AI 퀴즈 생성을 시작합니다."""
    lecture = db.query(models.Lecture).filter(
        models.Lecture.id == lecture_id, 
        models.Lecture.user_id == current_user.id
    ).first()
    
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    # 1. 퀴즈 객체 생성
    new_quiz = models.Quiz(
        lecture_id=lecture_id,
        user_id=current_user.id,
        title=f"{lecture.title} 복습 퀴즈"
    )
    db.add(new_quiz)
    db.flush()

    # 2. 비동기 작업 생성
    new_task = models.AITask(
        user_id=current_user.id,
        type="quiz_generation",
        status=models.TaskStatus.PENDING,
        progress=0
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_quiz)
    
    new_quiz.task_id = new_task.task_id

    # 3. 비동기 퀴즈 생성 작업 시작
    background_tasks.add_task(
        ai_service.run_quiz_generation,
        new_quiz.id,
        lecture.content,
        new_task.task_id,
        SessionLocal()
    )

    return new_quiz

@app.get("/quizzes/{quiz_id}", response_model=schemas.QuizResponse)
def get_quiz(quiz_id: UUID, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """특정 퀴즈의 문항들을 포함하여 조회합니다."""
    quiz = db.query(models.Quiz).filter(
        models.Quiz.id == quiz_id, 
        models.Quiz.user_id == current_user.id
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
    return new_result

@app.get("/quiz-results", response_model=List[schemas.QuizResultResponse])
def get_my_quiz_results(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """내가 수행한 모든 퀴즈 결과 내역을 가져옵니다."""
    return db.query(models.QuizResult).filter(models.QuizResult.user_id == current_user.id).all()
