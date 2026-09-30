# -*- coding: utf-8 -*-
"""
task_manager.py
백그라운드 비동기 작업 관리자:
1. 페이지 전환 시에도 에이전트 분석이 중단되지 않고 백그라운드에서 끝까지 실행
2. 세션별 진행 단계(Step 1~5) 실시간 추적 및 직관적인 st.status UI 연동
3. 분석 중 입력창 잠금 및 중복 실행 방지
"""

import sys
import uuid
import traceback
import threading
import time
import asyncio
from typing import Dict, Any, Optional, List
import db_manager

# 전역 작업 상태 딕셔너리
ACTIVE_TASKS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

STEPS = [
    (1, "🔍 DART 기업 개요 및 3개년 회계 결산 팩트 수집"),
    (2, "📊 Yahoo Finance 실시간 시세 및 언론사 최신 뉴스 수집"),
    (3, "🟢 Bull Analyst (롱 포지션) 성장 잠재력/Catalyst 분석"),
    (4, "🔴 Bear Analyst (숏 포지션) 주가 급락 원인 및 하방 리스크 검증"),
    (5, "📊 수석 투자분석가(CIO) 종합 분석 의견서 및 A4 PDF 보고서 발행")
]


def is_task_running(session_id: str) -> bool:
    """해당 세션에서 현재 에이전트가 실행 중인지 확인"""
    with _lock:
        task = ACTIVE_TASKS.get(session_id)
        return task is not None and task.get("status") == "running"


def get_task(session_id: str) -> Optional[Dict[str, Any]]:
    """세션의 작업 상태 조회"""
    with _lock:
        return ACTIVE_TASKS.get(session_id)


def clear_task(session_id: str) -> None:
    """완료되거나 확인된 작업 메모리 정리"""
    with _lock:
        if session_id in ACTIVE_TASKS:
            del ACTIVE_TASKS[session_id]


def update_task_step(session_id: str, step: int, desc: str, task_id: Optional[str] = None) -> None:
    """작업 진행 단계 업데이트 (작업 ID 일치 확인으로 경쟁 상태 방지)"""
    with _lock:
        if session_id in ACTIVE_TASKS:
            if task_id and ACTIVE_TASKS[session_id].get("task_id") != task_id:
                return
            ACTIVE_TASKS[session_id]["current_step"] = step
            ACTIVE_TASKS[session_id]["step_desc"] = desc
            completed = ACTIVE_TASKS[session_id]["completed_steps"]
            if desc not in completed:
                completed.append(desc)


def start_background_analysis(
    session_id: str,
    user_id: str,
    prompt: str,
    is_guest: bool = False
) -> str:
    """
    에이전트 분석을 백그라운드 데몬 쓰레드에서 시작합니다.
    작업 고유 ID(UUID)를 부여하여 경쟁 상태를 방지하고 DB에 안전하게 커밋합니다.
    """
    from agent_builder import execute_agent

    task_id = str(uuid.uuid4())
    with _lock:
        ACTIVE_TASKS[session_id] = {
            "task_id": task_id,
            "status": "running",
            "current_step": 1,
            "step_desc": STEPS[0][1],
            "prompt": prompt,
            "response": None,
            "error": None,
            "error_traceback": None,
            "start_time": time.time(),
            "completed_steps": [STEPS[0][1]],
            "is_guest": is_guest,
            "user_id": user_id
        }

    def _worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            def step_cb(step_num: int, step_desc: str):
                update_task_step(session_id, step_num, step_desc, task_id=task_id)

            response = loop.run_until_complete(
                execute_agent(prompt, session_id, step_callback=step_cb)
            )

            # 회원인 경우 DB에 즉시 어시스턴트 답변 커밋 (페이지 이동 중이어도 영구 저장)
            if not is_guest and user_id:
                db_manager.add_message(session_id, user_id, "assistant", response)

            with _lock:
                if session_id in ACTIVE_TASKS and ACTIVE_TASKS[session_id].get("task_id") == task_id:
                    ACTIVE_TASKS[session_id]["status"] = "done"
                    ACTIVE_TASKS[session_id]["response"] = response
                    ACTIVE_TASKS[session_id]["current_step"] = 5
        except Exception as e:
            err_msg = str(e)
            tb = traceback.format_exc()
            sys.stderr.write(f"[TaskManager Error] Task {task_id} failed: {err_msg}\n{tb}\n")
            with _lock:
                if session_id in ACTIVE_TASKS and ACTIVE_TASKS[session_id].get("task_id") == task_id:
                    ACTIVE_TASKS[session_id]["status"] = "error"
                    ACTIVE_TASKS[session_id]["error"] = err_msg
                    ACTIVE_TASKS[session_id]["error_traceback"] = tb

            if not is_guest and user_id:
                err_text = f"⚠️ 기업 분석 실행 중 오류가 발생했습니다: {err_msg}"
                try:
                    db_manager.add_message(session_id, user_id, "assistant", err_text)
                except Exception as db_err:
                    sys.stderr.write(f"[TaskManager Error] DB commit failed: {db_err}\n")
        finally:
            loop.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return task_id

