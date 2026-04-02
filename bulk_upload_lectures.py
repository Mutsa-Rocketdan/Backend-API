"""일괄 업로드: AI-Pipeline/강의 커리큘럼.csv + 강의 스크립트/*.txt → Backend-API /lectures

전제:
- 터널 URL로 접근 가능
- test2@naver.com (ADMIN) 계정으로 로그인 가능
"""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests


_ROOT = Path(__file__).resolve().parent.parent
_FRONT_ENV = _ROOT / "Frontend-APP" / ".env"


def _read_frontend_api_url() -> str | None:
    """Frontend-APP/.env 의 VITE_API_URL을 읽어 API Base URL로 사용."""
    if not _FRONT_ENV.is_file():
        return None
    try:
        txt = _FRONT_ENV.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(r"^\s*VITE_API_URL\s*=\s*(.+?)\s*$", txt, flags=re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip("\"'").rstrip("/")
    return val or None


API_BASE_URL = (
    os.getenv("API_BASE_URL")
    or os.getenv("TUNNEL")
    or _read_frontend_api_url()
)
if not API_BASE_URL:
    raise RuntimeError(
        "API_BASE_URL/TUNNEL 환경변수 또는 Frontend-APP/.env의 VITE_API_URL이 필요합니다."
    )

# 어떤 ADMIN 계정이든 사용 가능하도록 하드코딩 제거
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# 업로드 본문이 너무 길면 422/413을 유발할 수 있어 안전 상한을 둠
MAX_CONTENT_CHARS = 50_000


def _login_token(email: str, password: str) -> str:
    r = requests.post(
        f"{API_BASE_URL}/login",
        data={"username": email, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _read_curriculum_rows(csv_path: Path) -> list[dict[str, str]]:
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _script_path_for_date(scripts_dir: Path, date_str: str) -> Path:
    # 파일명 규칙: YYYY-MM-DD_*.txt
    matches = sorted(scripts_dir.glob(f"{date_str}_*.txt"))
    if not matches:
        raise FileNotFoundError(f"스크립트 파일 없음: {scripts_dir} / {date_str}_*.txt")
    return matches[0]


def _upload_one(headers: dict[str, str], row: dict[str, str], script_path: Path) -> dict[str, Any]:
    content = script_path.read_text(encoding="utf-8", errors="replace")
    payload = {
        "title": f"{row['subject']} - {row['content']}",
        "content": content[:MAX_CONTENT_CHARS],
        "week": int(row["week"]) if row.get("week") else None,
        "subject": row.get("subject") or None,
        "instructor": row.get("instructor") or None,
        "session": row.get("session") or None,
        "date": row.get("date") or None,
        "learning_goal": row.get("learning_goal") or None,
        "has_code_quiz": True,
        "is_active": True,
    }
    r = requests.post(f"{API_BASE_URL}/lectures", json=payload, headers=headers, timeout=120)
    is_json = r.headers.get("content-type", "").startswith("application/json")
    return {
        "status_code": r.status_code,
        "json": (r.json() if is_json else None),
        "text": r.text,
    }


def main() -> None:
    base = Path("/AI-Pipeline")
    csv_path = base / "강의 커리큘럼.csv"
    scripts_dir = base / "강의 스크립트"

    email = ADMIN_EMAIL
    password = ADMIN_PASSWORD
    if len(sys.argv) >= 3:
        email = sys.argv[1]
        password = sys.argv[2]
    if not email or not password:
        raise RuntimeError(
            "ADMIN_EMAIL/ADMIN_PASSWORD 환경변수 또는 인자(email password)가 필요합니다.\n"
            "예) python bulk_upload_lectures.py admin@site.com password123"
        )

    token = _login_token(email, password)
    headers = {"Authorization": f"Bearer {token}"}

    rows = _read_curriculum_rows(csv_path)
    # 스크립트 파일이 존재하는 날짜들만 대상으로 업로드 (현재 폴더: 15개)
    script_files = sorted(scripts_dir.glob("*.txt"))
    dates = sorted({p.name.split("_", 1)[0] for p in script_files if "_" in p.name})

    # 커리큘럼은 오전/오후 2행이 있을 수 있는데, 스크립트는 날짜당 1파일 → 날짜 기준 1행만 선택(오전 우선)
    rows_by_date: dict[str, dict[str, str]] = {}
    for r in rows:
        d = (r.get("date") or "").strip()
        if not d:
            continue
        # 오전 우선, 없으면 첫 행
        if d not in rows_by_date:
            rows_by_date[d] = r
        else:
            if (rows_by_date[d].get("session") or "") != "오전" and (r.get("session") or "") == "오전":
                rows_by_date[d] = r

    print(f"API Base URL: {API_BASE_URL}")
    print(f"Scripts: {len(script_files)} files, Dates: {len(dates)}")

    ok, fail = 0, 0
    results: list[dict[str, Any]] = []
    for d in dates:
        row = rows_by_date.get(d)
        if not row:
            fail += 1
            results.append({"date": d, "ok": False, "error": "커리큘럼 행 없음"})
            continue
        try:
            sp = _script_path_for_date(scripts_dir, d)
            resp = _upload_one(headers, row, sp)
            if resp["status_code"] == 200 and resp["json"] and resp["json"].get("id"):
                ok += 1
                results.append({"date": d, "ok": True, "lecture_id": resp["json"]["id"], "task_id": resp["json"].get("task_id")})
            else:
                fail += 1
                results.append({"date": d, "ok": False, "status_code": resp["status_code"], "body": resp["text"][:300]})
        except Exception as e:
            fail += 1
            results.append({"date": d, "ok": False, "error": str(e)})

    print(f"\n=== DONE ===\nOK: {ok}, FAIL: {fail}\n")
    for r in results:
        if r.get("ok"):
            print(f"[OK]  {r['date']} lecture_id={r['lecture_id']} task_id={r.get('task_id')}")
        else:
            print(f"[FAIL]{r.get('date','?')} {r.get('status_code','')} {r.get('error','')} {r.get('body','')}")


if __name__ == "__main__":
    main()

