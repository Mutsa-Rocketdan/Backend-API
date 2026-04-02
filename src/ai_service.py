"""AI-Pipeline 호출 래퍼 — 인제스트(전역 벡터DB) + RAG 기반 생성.

강의 업로드 시 본문을 ``ingest_lecture_upload``로 FAISS에 반영한 뒤,
개념·퀴즈·가이드 생성은 ``lecture_id``로 RAG 검색한 컨텍스트를 사용합니다.
AI-Pipeline을 import할 수 없는 환경에서는 기존 모의(mock) 데이터로 폴백합니다.
"""

import sys
import time
import uuid
import traceback
from pathlib import Path

from sqlalchemy.orm import Session

import models

# ---------------------------------------------------------------------------
# AI-Pipeline import 시도
# Backend 와 AI-Pipeline 모두 `src` 패키지를 사용하므로 충돌을 피하기 위해
# importlib 로 AI-Pipeline/src 를 `ai_pipeline` 이라는 별도 패키지로 등록합니다.
# 내부 상대 import(from .common …) 가 ai_pipeline.common 으로 올바르게 해석됩니다.
# ---------------------------------------------------------------------------
_AI_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent / "AI-Pipeline"
_AI_AVAILABLE = False

try:
    import importlib.util

    _ai_src = _AI_PIPELINE_ROOT / "src"
    if _ai_src.is_dir():
        _pkg_spec = importlib.util.spec_from_file_location(
            "ai_pipeline",
            str(_ai_src / "__init__.py"),
            submodule_search_locations=[str(_ai_src)],
        )
        if _pkg_spec is None or _pkg_spec.loader is None:
            raise ImportError("Failed to create module spec for AI-Pipeline package")
        _pkg = importlib.util.module_from_spec(_pkg_spec)
        sys.modules["ai_pipeline"] = _pkg
        _pkg_spec.loader.exec_module(_pkg)

        from ai_pipeline.api_interface import (
            generate_concepts,
            generate_quiz_questions,
            generate_study_guide,
        )
        from ai_pipeline.ingest_lecture import ingest_lecture_upload
        _AI_AVAILABLE = True
except Exception as _exc:
    print(f"[ai_service] AI-Pipeline import 실패: {_exc}")
    traceback.print_exc()
    _AI_AVAILABLE = False


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def update_task_status(
    db: Session,
    task_id: uuid.UUID,
    status: models.TaskStatus = None,
    progress: int = None,
):
    """DB의 AITask 상태를 실시간으로 업데이트합니다."""
    task = db.query(models.AITask).filter(models.AITask.task_id == task_id).first()
    if task:
        if status:
            task.status = status
        if progress is not None:
            task.progress = progress
        db.commit()


def _lecture_date_str(lecture: models.Lecture | None) -> str | None:
    if lecture is None or lecture.date is None:
        return None
    return lecture.date.isoformat()


# ---------------------------------------------------------------------------
# 1. 개념 추출 (업로드 시 전역 DB 인제스트 후 RAG)
# ---------------------------------------------------------------------------

def run_concept_extraction(
    lecture_id: str,
    content: str,
    task_id: uuid.UUID,
    db: Session,
):
    """강의 본문을 벡터DB에 반영한 뒤, RAG 컨텍스트로 개념을 추출·저장합니다."""
    try:
        update_task_status(db, task_id, status=models.TaskStatus.PROCESSING, progress=10)

        lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id).first()
        lid = str(lecture_id)

        if _AI_AVAILABLE:
            update_task_status(db, task_id, progress=18)
            ingest_lecture_upload(
                content,
                lecture_id=lid,
                week=lecture.week if lecture else None,
                subject=lecture.subject if lecture else None,
                instructor=lecture.instructor if lecture else None,
                session=lecture.session if lecture else None,
                date_str=_lecture_date_str(lecture),
                title=lecture.title if lecture else None,
            )
            update_task_status(db, task_id, progress=45)
            concepts = generate_concepts(content, lecture_id=lid)
            update_task_status(db, task_id, progress=80)
        else:
            time.sleep(1)
            update_task_status(db, task_id, progress=30)
            time.sleep(1)
            concepts = [
                {"concept_name": "핵심 개념 (mock)", "description": "AI-Pipeline 미연결 상태의 모의 데이터입니다.", "mastery_score": 0.0},
                {"concept_name": "세부 주제 (mock)", "description": "AI-Pipeline 패키지를 설치하면 실제 생성으로 전환됩니다.", "mastery_score": 0.0},
            ]
            update_task_status(db, task_id, progress=80)

        for c in concepts:
            db.add(models.Concept(
                lecture_id=lecture_id,
                concept_name=c["concept_name"],
                description=c.get("description", ""),
                mastery_score=c.get("mastery_score", 0.0),
            ))

        update_task_status(db, task_id, status=models.TaskStatus.COMPLETED, progress=100)
        db.commit()

    except Exception as e:
        update_task_status(db, task_id, status=models.TaskStatus.FAILED, progress=0)
        print(f"[ai_service] concept_extraction 실패 ({task_id}): {e}")
        traceback.print_exc()
        db.commit()


# ---------------------------------------------------------------------------
# 2. 퀴즈 생성 (동일 강의는 이미 인제스트됨 → RAG)
# ---------------------------------------------------------------------------

def run_quiz_generation(
    quiz_id: uuid.UUID,
    lecture_id: uuid.UUID,
    lecture_content: str,
    task_id: uuid.UUID,
    db: Session,
    *,
    quiz_type: str = "multiple_choice",
    quiz_types: list[str] | None = None,
    difficulty: str = "medium",
    count: int = 5,
):
    """강의별 RAG 컨텍스트로 퀴즈 문항을 생성하여 DB에 저장합니다."""
    try:
        update_task_status(db, task_id, status=models.TaskStatus.PROCESSING, progress=10)

        lid = str(lecture_id)

        if _AI_AVAILABLE:
            update_task_status(db, task_id, progress=30)
            questions = generate_quiz_questions(
                content=lecture_content,
                quiz_type=quiz_type,
                quiz_types=quiz_types,
                difficulty=difficulty,
                count=count,
                lecture_id=lid,
            )
            update_task_status(db, task_id, progress=80)
        else:
            time.sleep(1)
            update_task_status(db, task_id, progress=40)
            time.sleep(1)
            questions = [
                {
                    "question_text": "다음 중 올바른 설명은? (mock)",
                    "options": ["보기1", "보기2", "보기3", "보기4"],
                    "correct_answer": "보기1",
                    "explanation": "AI-Pipeline 미연결 상태의 모의 데이터입니다.",
                    "quiz_type": quiz_type,
                    "difficulty": difficulty,
                },
            ]
            update_task_status(db, task_id, progress=80)

        if not questions:
            raise ValueError(f"생성된 퀴즈 문항이 0개입니다. quiz_type={quiz_type}, difficulty={difficulty}, count={count}")

        for q in questions:
            db.add(models.QuizQuestion(
                quiz_id=quiz_id,
                question_text=q["question_text"],
                options=q.get("options", []),
                correct_answer=q["correct_answer"],
                explanation=q.get("explanation", ""),
                quiz_type=q.get("quiz_type", quiz_type),
                difficulty=q.get("difficulty", difficulty),
            ))

        update_task_status(db, task_id, status=models.TaskStatus.COMPLETED, progress=100)
        db.commit()

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        update_task_status(db, task_id, status=models.TaskStatus.FAILED, progress=0)
        print(f"[ai_service] quiz_generation 실패 ({task_id}): {e}")
        traceback.print_exc()
        db.commit()


# ---------------------------------------------------------------------------
# 3. 학습 가이드 생성 (RAG 전체 청크 우선)
# ---------------------------------------------------------------------------

def run_guide_generation(
    lecture_id: uuid.UUID,
    content: str,
    task_id: uuid.UUID,
    db: Session,
):
    """강의별 RAG 컨텍스트로 학습 가이드를 생성하여 DB에 저장합니다."""
    try:
        update_task_status(db, task_id, status=models.TaskStatus.PROCESSING, progress=20)

        lid = str(lecture_id)

        if _AI_AVAILABLE:
            update_task_status(db, task_id, progress=40)
            guide_data = generate_study_guide(content, lecture_id=lid)
            update_task_status(db, task_id, progress=80)
        else:
            time.sleep(1)
            update_task_status(db, task_id, progress=60)
            time.sleep(1)
            guide_data = {
                "summary": "AI-Pipeline 미연결 상태의 모의 요약입니다.",
                "key_summaries": ["핵심 요약 1 (mock)", "핵심 요약 2 (mock)"],
                "review_checklist": ["복습 항목 1 (mock)", "복습 항목 2 (mock)"],
                "concept_map": {"nodes": ["개념A", "개념B"], "edges": [{"from": "개념A", "to": "개념B"}]},
            }
            update_task_status(db, task_id, progress=80)

        # 강의당 가이드는 1개(Unique)라서, 이미 있으면 update로 처리
        existing = db.query(models.Guide).filter(models.Guide.lecture_id == lecture_id).first()
        if existing:
            existing.summary = guide_data.get("summary", "")
            existing.key_summaries = guide_data.get("key_summaries", [])
            existing.review_checklist = guide_data.get("review_checklist", [])
            existing.concept_map = guide_data.get("concept_map", {})
        else:
            db.add(models.Guide(
                lecture_id=lecture_id,
                summary=guide_data.get("summary", ""),
                key_summaries=guide_data.get("key_summaries", []),
                review_checklist=guide_data.get("review_checklist", []),
                concept_map=guide_data.get("concept_map", {}),
            ))

        update_task_status(db, task_id, status=models.TaskStatus.COMPLETED, progress=100)
        db.commit()

    except Exception as e:
        # INSERT/FLUSH 실패(유니크 충돌 등) 시 세션이 rollback 상태가 되므로 먼저 rollback
        try:
            db.rollback()
        except Exception:
            pass
        update_task_status(db, task_id, status=models.TaskStatus.FAILED, progress=0)
        print(f"[ai_service] guide_generation 실패 ({task_id}): {e}")
        traceback.print_exc()
        try:
            db.commit()
        except Exception:
            pass
