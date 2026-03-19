# Backend Implementation Plan: PostgreSQL & FastAPI Integration

이 문서는 PostgreSQL 기반의 백엔드 데이터베이스 구축 및 API 서버 전환의 **구현 단계와 진행 상황**을 관리합니다. 상세한 데이터베이스 설계 및 아키텍처 정보는 [Database Schema 명세서](./backend_db_schema.md)를 참조하세요.

---

## 1. 시스템 요약 (Summary)

- **핵심 기술**: FastAPI, PostgreSQL 16, SQLAlchemy, Alembic, Docker
- **연동 방식**: Cloudflare Tunnel (External API Port: 8001)
- **데이터 구조**: [상세 ERD 및 테이블 명세 바로가기](./backend_db_schema.md)

---

## 3. 구현 단계 (Execution Phases)

### Phase 1: 인프라 및 Docker 환경 설정
- [x] `Dockerfile` 가동 (Python 3.11-slim 기반 환경 구축)
- [x] `docker-compose.yml` 작성
    - **PostgreSQL 서비스**: 타 프로젝트와의 충돌 방지를 위해 외부 포트 `5433` (혹은 가용 포트) 할당
    - **API 서비스**: FastAPI 서버 컨테이너화
- [x] `.env` 파일을 통한 PostgreSQL 연결 정보 및 Docker 환경 변수 관리
- [x] 기본 의존성 추가: `psycopg2-binary`, `sqlalchemy`, `fastapi`, `alembic`, `uvicorn`
- [x] SQLAlchemy `engine` 및 `SessionLocal` 설정
- [x] **External Connectivity**: 도메인 없이 Cloudflare Tunnel(Quick Tunnel) 연동 완료 (8001 포트 기반)


### Phase 2: 데이터 모델링 및 마이그레이션
- [x] `models.py` 내 테이블 정의
- [x] Alembic을 이용한 DB 초기 스키마 생성 및 마이그레이션 수행

### Phase 3: 인증 시스템 구축
- [x] OAuth2PasswordBearer를 이용한 JWT 토큰 발급 로직 구현
- [x] Password Hashing (passlib) 적용
- [x] `Current User` 의존성 주입(DI) 구현

### Phase 4: API 엔드포인트 개발
- [x] User CRUD API (회원가입/정보조회 완료)
- [x] 강의 자료 업로드 및 목록 조회 API 구현
- [x] 비동기 지식(개념) 추출 구조 구축 및 조회 API
- [x] Quiz Result 저장 및 조회 API
- [x] 기존 Streamlit 로직을 비동기 API 내부로 래핑 (ai_service 구조화 완료)


### Phase 5: 외부 접속 및 앱 연동 전략 (External Connectivity)

모바일 앱 등 외부 환경에서 로컬 백엔드에 접속하기 위한 단계별 옵션입니다.

- **Option 1: Cloudflare Tunnel (현재 적용됨)**
    - **특징**: ngrok과 유사하나 무료로 HTTPS 터널링 제공. 
    - **설정**: `docker-compose.yml` 내 `tunnel` 서비스 통합 완료.

- **Option 2: Local Network (동일 Wi-Fi 내 개발)**
    - **특징**: PC의 로컬 IP(192.168.x.x)를 이용하여 직접 접속.
    - **설정**: FastAPI 가동 시 `0.0.0.0` 바인딩 필수.

- **Option 3: 클라우드 기반 무료 배포 (Render/Railway)**
    - **특징**: 코드 혹은 Docker 이미지를 올려 웹상에 상시 구동.


### Phase 6: 모니터링 및 관측성 (Observability)

#### **Essential (필수 적용 - 가성비 및 안정성 우선)**
- [x] **Sentry**: 실시간 에러 트래킹 및 코드 단위 예외 알림
- [x] **Prometheus & Grafana**: 서버 핵심 메트릭 수집 및 통합 대시보드 시각화
    - [x] `prometheus-fastapi-instrumentator`를 통한 `/metrics` 엔드포인트 개설
    - [x] `docker-compose.yml` 내 Prometheus 서비스 추가 및 스크래핑 설정 (`prometheus.yml`)
    - [x] `docker-compose.yml` 내 Grafana 서비스 추가 및 대시보드 연동

#### **Optional (선택적 확장 - 고도화 단계)**
- [ ] **Loki**: 로그 중앙 집중화 및 텍스트 로그 시각화 검색
- [ ] **PostgreSQL Exporter**: 데이터베이스 연결 및 쿼리 성능 세부 모니터링
- [ ] **cAdvisor**: 도커 컨테이너 하드웨어 리소스(CPU/MEM) 정밀 추적


### Phase 7: 서비스 보안 강화 (Production Security & Hardening)

#### **Essential (필수 적용 - 가성비 및 즉각적 방어)**
- [x] **CORS (Cross-Origin Resource Sharing) 설정**: 허용된 도메인 외의 API 접근 차단
- [x] **IP 기반 Rate Limiting (SlowAPI)**: 특정 IP의 과도한 요청 차단 및 DOS 공격 방어
- [x] **API 문서(/docs) 보호**: Swagger UI에 Basic Auth 보안 적용
- [x] **Security Headers 설정**: FastAPI 기본 및 미들웨어를 통한 보안 설정 완료

#### **Hardened (강화 항목 - 시스템 견고성 최적화)**
- [ ] **Pydantic Strict Mode**: 모든 API 입력 데이터의 엄격한 스키마 검증
- [ ] **정적 보안 분석 (Static Analysis)**: Bandit 및 Safety 툴을 활용한 정기 스캔
- [ ] **ORM 패턴 전수 검사**: 모든 DB 접근에 Parameterized Query 사용 강제
- [ ] **Secrets Audit**: .env 파일 외 코드 내 비밀 정보 하드코딩 여부 전수 조사
- [x] **Step 1: DB 스키마 업데이트 (확장성 및 데이터 보존)**: 
    - `models.py`의 `User` 모델에 `role` (Enum: USER, ADMIN) 컬럼 추가.
    - `Lecture` 및 `Quiz` 테이블에 `is_active` (Boolean, default=True) 필드 추가 (Soft Delete용).
- [x] **Step 2: Pydantic 스키마 정교화**: `schemas.py`의 `UserResponse` 업데이트 및 `role` 필드 보호(유저 직접 수정 불가).
- [x] **Step 3: Security Guard 구현**: `auth.py` 내에 권한별로 판정 가능한 의존성(`RequireRole(["ADMIN"])` 등) 추가.
- [x] **Step 4: API 분리 및 보호 (Soft Delete)**: 
    - `app.py`에서 관리자 전용 라이팅(강의 업로드) 기능 가드 적용.
    - 데이터 삭제 요청 시 DB 레코드 삭제 대신 `is_active=False`로 변경하여 유저의 `QuizResult` 통계 보존.
- [x] **Step 5: 조회(Query) 가드 반영**: 일반 소비자의 `GET` 요청 시 `is_active=True`인 레코드만 반환되도록 GET API 필터링 보완.
- [x] **Step 6: 데이터베이스 마이그레이션**: Alembic을 이용해 실제 DB에 Role 체계 및 Soft Delete 필드 반영.


## 4. AI 기술 협의 및 향후 고도화 이슈 (AI Technical Update & Roadmap)

AI 파이프라이닝 팀과의 논의(2026-03-19)를 통해 도출된 핵심 업데이트 및 장기적 인프라 고려 사항입니다.

### **[데이터 입력 및 머지 전략]**
- **입력 방식의 유연성**: 현재 JSON 내 `string` 기반 직접 입력을 기본으로 유지하되, 향후 대용량 데이터 및 정형 데이터 처리를 위한 **파일 업로드(CSV/TXT 파일 형태)** 방식 도입 고려.
- **머지 프로토콜**: 로컬 개발과 실제 AI 연산 결과값의 정합성을 보장하기 위한 머지(Merge) 전략 정립 필요.

### **[어드민 권한 및 보안 모델]**
- **Admin 전용 권한 부여**: 새로운 스크립트 업로드 및 DB 핵심 스키마 권한(수정/삭제)은 **관리자(Admin)** 계정에만 부여하여 데이터 무결성 보호.
- **RBAC (Role-Based Access Control)**: 사용자 역할별 세분화된 API 접근 제어 로직 구현 예정.

### **[결과물 패키징 및 차별점 발굴]**
- **종합 결과 패키징**: 단순히 퀴즈만 제공하는 단계를 넘어 `학습진행률 + 퀴즈 통계 + AI 학습 가이드`를 하나의 패키지로 묶어 완성도 높은 결과물 제공.
- **차별점(Differentiator)**: 기존 교육 앱 대비 사용자 경험과 기술적 측면에서의 독창적 경쟁력(예: 유사 개념 자동 연계 등) 강화 방안 검토.


## 5. 팀 협업 및 동적 주소 관리 (Collaboration Protocol)

> [!IMPORTANT]
> **분산 개발 환경에서의 통신 전략 (8001 Port & Dynamic URL)**
> - **Port Consistency**: 본 프로젝트의 백엔드는 호스트 머신의 **8001번 포트**를 기반으로 외부 노출(`API_EXTERNAL_PORT=8001`)됩니다.
> - **URL Propagation**: 가변형 URL(`trycloudflare.com`) 변경 시 가용 주소를 즉시 팀 채널에 공유합니다.
> - **Health Check**: 외부 접속 시 반드시 `/docs`를 통해 서버 가동 여부를 먼저 확인합니다.


## 6. 고려 사항 (Key Considerations)

- **Multi-Project Isolation**: Docker 프로젝트 이름 명시 (이름 충돌 방지).
- **Scalability**: 데이터 증가에 따른 인덱싱 및 페이지네이션 전략 수립.
- **Vector DB Consolidation**: `pgvector` 기반 벡터 검색 통합 관리 고려.
- **Security**: HTTPS 상에서 JWT 토큰 검증 및 CORS 설정 필수.
- **Performance**: 비동기 작업 트래킹(`AITasks`) 및 결과 캐싱 도입 검토.
- **Maintainability**: 클라이언트 앱 호환성을 위한 API 버전 관리(`/v1`) 전략.

---
작성일: 2026-03-18 (Phase 7 보안 강화 추가 및 구조 정제)
작성자: Antigravity Assistant

---
작성일: 2026-03-19 (AI 파이프라인 협의 결과 반영 - 입력 방식 및 어드민 권한 추가)
작성자: Antigravity Assistant
