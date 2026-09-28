import os
import re
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("file-server")

# 상위 폴더의 output 디렉토리 절대경로 고정
OUTPUT_DIR = (Path(__file__).parent.parent / "output").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 최대 5MB

def sanitize_filename(filename: str) -> str:
    """파일명에서 경로 조작 문자 및 운영체제 금지 문자 제거"""
    name = Path(filename).name
    # 윈도우/리눅스 특수문자 치환 (\ / : * ? " < > |)
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    if not name or name == ".md":
        name = "기업_분석_보고서.md"
    if not name.endswith(".md"):
        name += ".md"
    return name

def sanitize_session_id(session_id: str) -> str:
    """세션 ID 디렉토리명 안전 검증"""
    if not session_id:
        return "default"
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '', session_id).strip()
    return clean if clean else "default"

@mcp.tool("write_markdown", description="분석된 기업 보고서나 요약 내용을 마크다운(.md) 파일로 저장합니다. session_id를 전달하면 해당 대화방 전용 폴더에 분리 저장됩니다.")
def write_markdown(filename: str, content: str, session_id: str = "default") -> str:
    """
    기업 분석 결과나 재무 분석 보고서를 마크다운 파일로 대화방별 분리하여 안전하게 저장합니다.

    Args:
        filename: 저장할 파일명 (예: '삼성전자_2025_분석보고서.md')
        content: 파일에 기록할 마크다운 형식의 보고서 본문
        session_id: 현재 대화 세션 식별자 (대화방별 파일 분리용)
    """
    try:
        if not content:
            return "[오류] 저장할 본문 내용이 비어있습니다."

        if len(content.encode("utf-8")) > MAX_CONTENT_LENGTH:
            return "[오류] 보고서 용량이 허용치(5MB)를 초과하여 저장할 수 없습니다."

        clean_filename = sanitize_filename(filename)
        clean_session = sanitize_session_id(session_id)
        
        target_dir = (OUTPUT_DIR / clean_session).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = (target_dir / clean_filename).resolve()

        # Path Traversal 방어 검증 (타깃 경로가 OUTPUT_DIR 내부인지 확인)
        if not str(target_path).startswith(str(OUTPUT_DIR)):
            return "[보안 오류] 잘못된 파일 경로 접근이 감지되었습니다."

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"[성공] 분석 보고서가 '{clean_filename}'(대화방: {clean_session})에 성공적으로 저장되었습니다."
    except Exception as e:
        return f"[오류] 보고서 파일 저장 중 문제가 발생했습니다: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
