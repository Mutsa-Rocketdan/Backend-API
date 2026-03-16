import time
import uuid
from sqlalchemy.orm import Session
import models
from datetime import datetime

# --- AI 하이퍼파라미터 및 설정 ---
# 나중에 이 값들만 수정하여 AI의 행동을 조절할 수 있습니다.
AI_CONFIG = {
    "model_name": "gpt-4o",        # 사용할 모델명
    "temperature": 0.7,            # 창의성 조절 (0.0 ~ 1.0)
    "max_tokens": 1000,            # 응답 최대 길이
    "chunk_size": 600,             # 텍스트를 자르는 단위 (토큰 기준)
    "chunk_overlap": 100,          # 자를 때 겹치는 부분의 크기
}

def run_concept_extraction(lecture_id: str, content: str, task_id: uuid.UUID, db: Session):
    """
    강의 자료에서 지식을 추출하는 AI 프로세스 시뮬레이터입니다.
    이 함수 내부의 주석 부분을 실제 AI 로직으로 갈아끼우면 됩니다.
    """
    try:
        # [단계 1] 작업 시작 알림 (Progress: 10%)
        update_task_status(db, task_id, status=models.TaskStatus.PROCESSING, progress=10)
        time.sleep(1) # AI 처리를 기다리는 척 (실제 요청 시 삭제)

        # [단계 2] 텍스트 전처리 및 청킹
        # TODO: src/preprocessing.py의 chunk_text() 함수 등을 여기서 호출하세요.
        # chunks = preprocessing.chunk_text(content, max_tokens=AI_CONFIG["chunk_size"])
        update_task_status(db, task_id, progress=30)
        time.sleep(1)

        # [단계 3] AI 모델 호출 (개념 추출)
        # TODO: 아래는 가짜 데이터입니다. 실제로는 openai API 등을 호출하여 결과물(JSON 등)을 받으세요.
        # response = openai.ChatCompletion.create(model=AI_CONFIG["model_name"], messages=...)
        # mock_data = response.choices[0].message.content
        update_task_status(db, task_id, progress=70)
        time.sleep(1)

        # [단계 4] 추출된 데이터를 DB에 저장
        mock_concepts = [
            {"name": f"핵심 개념 (AI 모델: {AI_CONFIG['model_name']})", "desc": "강의에서 추출된 첫 번째 지식입니다."},
            {"name": "세부 주제 X", "desc": "강의의 중간 부분에서 언급된 중요한 포인트입니다."}
        ]
        
        for c in mock_concepts:
            new_concept = models.Concept(
                lecture_id=lecture_id,
                concept_name=c["name"],
                description=c["desc"],
                mastery_score=0.0
            )
            db.add(new_concept)
        
        # [단계 5] 모든 작업 완료
        update_task_status(db, task_id, status=models.TaskStatus.COMPLETED, progress=100)
        db.commit()

    except Exception as e:
        # 에러 발생 시 상태 기록
        update_task_status(db, task_id, status=models.TaskStatus.FAILED, progress=0)
        print(f"Error in AI task {task_id}: {str(e)}")
        db.commit()

def run_quiz_generation(quiz_id: uuid.UUID, lecture_content: str, task_id: uuid.UUID, db: Session):
    """
    AI를 사용하여 퀴즈 문항을 생성하는 프로세스 시뮬레이터입니다.
    """
    try:
        update_task_status(db, task_id, status=models.TaskStatus.PROCESSING, progress=10)
        time.sleep(1)

        # [단계 2] 강의 내용 분석 및 문제 초안 작성
        update_task_status(db, task_id, progress=40)
        time.sleep(1)

        # [단계 3] AI 모델 호출 (퀴즈 문항 생성)
        # TODO: 실제 AI 프롬프트를 사용하여 객관식 문제를 생성하세요.
        update_task_status(db, task_id, progress=80)
        time.sleep(1)

        # [단계 4] 생성된 문항 저장
        mock_questions = [
            {
                "text": "파이썬에서 리스트의 길이를 구하는 함수는?",
                "options": ["size()", "length()", "len()", "count()"],
                "answer": "len()",
                "explanation": "len() 함수는 파이썬 내장 함수로 시퀀스의 길이를 반환합니다."
            },
            {
                "text": "다음 중 파이썬의 데이터 타입이 아닌 것은?",
                "options": ["int", "float", "double", "str"],
                "answer": "double",
                "explanation": "파이썬에서는 소수점을 float으로 처리하며 double은 별도로 존재하지 않습니다."
            }
        ]

        for q in mock_questions:
            new_question = models.QuizQuestion(
                quiz_id=quiz_id,
                question_text=q["text"],
                options=q["options"],
                correct_answer=q["answer"],
                explanation=q["explanation"]
            )
            db.add(new_question)

        # [단계 5] 완료
        update_task_status(db, task_id, status=models.TaskStatus.COMPLETED, progress=100)
        db.commit()

    except Exception as e:
        update_task_status(db, task_id, status=models.TaskStatus.FAILED, progress=0)
        print(f"Error in Quiz generation task {task_id}: {str(e)}")
        db.commit()

def update_task_status(db: Session, task_id: uuid.UUID, status: models.TaskStatus = None, progress: int = None):
    """DB의 AITask 상태를 실시간으로 업데이트합니다."""
    task = db.query(models.AITask).filter(models.AITask.task_id == task_id).first()
    if task:
        if status:
            task.status = status
        if progress is not None:
            task.progress = progress
        db.commit()
