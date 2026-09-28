import sqlite3
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from config import DB_PATH

_is_db_initialized = False

def hash_password(password: str) -> str:
    """비밀번호 SHA-256 해시 생성"""
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()

def get_connection() -> sqlite3.Connection:
    """SQLite 커넥션 생성 (WAL 모드 및 외래키 제약조건 활성화)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(force: bool = False) -> None:
    """데이터베이스 및 테이블, 성능 최적화 인덱스 초기화 (1회만 실행)"""
    global _is_db_initialized
    if _is_db_initialized and not force:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. 사용자 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 기존 테이블에 password_hash 컬럼이 없는 경우 안전하게 추가 (마이그레이션)
        cursor.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "password_hash" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        
        # 2. 대화 세션 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # 3. 메시지 히스토리 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # 4. 성능 최적화 인덱스 (대화 목록 및 메시지 조회 속도 대폭 개선)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);")
            
        conn.commit()

    _is_db_initialized = True

# --- 인증 및 사용자 관련 함수 ---
def signup_user(user_id: str, username: str, password: str) -> Tuple[bool, str]:
    """신규 회원가입"""
    init_db()
    uid = user_id.strip()
    uname = username.strip()
    pwd = password.strip()

    if not uid or not uname or not pwd:
        return False, "아이디, 닉네임, 비밀번호를 모두 입력해주세요."
    if len(pwd) < 4:
        return False, "비밀번호는 최소 4자 이상이어야 합니다."

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash) VALUES (?, ?, ?)",
                (uid, uname, hash_password(pwd))
            )
            conn.commit()
            return True, "회원가입이 완료되었습니다."
    except sqlite3.IntegrityError:
        return False, "이미 존재하는 사용자 아이디입니다."
    except Exception as e:
        return False, f"회원가입 중 오류가 발생했습니다: {str(e)}"

def login_user(user_id: str, password: str) -> Optional[Dict]:
    """로그인 검증 (성공 시 사용자 정보 dict 반환)"""
    init_db()
    uid = user_id.strip()
    pwd_hash = hash_password(password.strip())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, username, created_at, password_hash FROM users WHERE user_id = ?",
            (uid,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        # 비밀번호 확인 (기존 비밀번호 없는 유저 호환 또는 비밀번호 일치)
        stored_hash = row["password_hash"]
        if stored_hash is None or stored_hash == pwd_hash:
            return {
                "user_id": row["user_id"],
                "username": row["username"],
                "created_at": row["created_at"]
            }
        return None

def get_users() -> List[Dict]:
    """등록된 모든 사용자 조회"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, created_at FROM users ORDER BY created_at ASC")
        return [dict(row) for row in cursor.fetchall()]

# --- 세션 관련 함수 ---
def get_sessions(user_id: str) -> List[Dict]:
    """특정 사용자의 대화 세션 목록 조회 (최신 수정순)"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT session_id, user_id, title, created_at, updated_at
            FROM sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

def create_session(user_id: str, session_id: str, title: str = "새로운 기업 분석") -> None:
    """새로운 대화 세션 생성"""
    init_db()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO sessions (session_id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, title, now, now)
        )
        conn.commit()

def update_session_title(session_id: str, title: str) -> None:
    """세션 제목 및 갱신 시각 업데이트"""
    init_db()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sessions
            SET title = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (title, now, session_id)
        )
        conn.commit()

def delete_session(session_id: str) -> None:
    """세션 및 관련 메시지 삭제"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()

# --- 메시지 관련 함수 ---
def get_messages(session_id: str) -> List[Dict]:
    """특정 세션의 모든 메시지 내역 조회 (시간순)"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, user_id, role, content, metadata_json, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

def add_message(session_id: str, user_id: str, role: str, content: str, metadata_json: Optional[str] = None) -> None:
    """대화 메시지 추가 및 세션 갱신일자 동시 업데이트 (트랜잭션)"""
    init_db()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (session_id, user_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, user_id, role, content, metadata_json, now)
        )
        cursor.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id)
        )
        conn.commit()

if __name__ == "__main__":
    init_db(force=True)
    print("✅ 데이터베이스가 성공적으로 초기화 및 인덱싱되었습니다:", DB_PATH)
