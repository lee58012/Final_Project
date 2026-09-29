import os
import sys
import re
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# 프로젝트 루트를 sys.path에 추가하여 pdf_generator 임포트 가능하도록 설정
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from pdf_generator import markdown_to_pdf_bytes
except Exception as e:
    markdown_to_pdf_bytes = None

mcp = FastMCP("file-server")

# 상위 폴더의 output 디렉토리 절대경로 고정
OUTPUT_DIR = (PROJECT_ROOT / "output").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 최대 5MB

def sanitize_filename(filename: str, ext: str = ".pdf") -> str:
    """파일명에서 경로 조작 문자 및 운영체제 금지 문자 제거하고 .pdf 확장자 보장"""
    name = Path(filename).name
    # 윈도우/리눅스 특수문자 치환 (\ / : * ? " < > |)
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    if not name or name == ext or name == ".md":
        name = f"기업_투자심의보고서{ext}"
    if name.endswith(".md"):
        name = name[:-3] + ext
    if not name.endswith(ext):
        name += ext
    return name

def sanitize_session_id(session_id: str) -> str:
    """세션 ID 디렉토리명 안전 검증"""
    if not session_id:
        return "default"
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '', session_id).strip()
    return clean if clean else "default"

@mcp.tool("write_pdf", description="분석된 투자 심의 보고서를 고품질 A4 PDF 파일로 변환하여 저장합니다. session_id를 전달하면 해당 대화방 전용 폴더에 분리 저장됩니다.")
def write_pdf(filename: str, content: str, session_id: str = "default") -> str:
    """
    기업 투자 심의 보고서를 PDF 파일로 대화방별 분리하여 안전하게 저장합니다.

    Args:
        filename: 저장할 파일명 (예: '삼성전자_가상투자심의보고서.pdf')
        content: 파일에 기록할 마크다운 형식의 보고서 본문 (PDF로 자동 변환됨)
        session_id: 현재 대화 세션 식별자 (대화방별 파일 분리용)
    """
    try:
        if not content:
            return "[오류] 저장할 본문 내용이 비어있습니다."

        if len(content.encode("utf-8")) > MAX_CONTENT_LENGTH:
            return "[오류] 보고서 용량이 허용치(5MB)를 초과하여 저장할 수 없습니다."

        clean_filename = sanitize_filename(filename, ext=".pdf")
        clean_session = sanitize_session_id(session_id)
        
        target_dir = (OUTPUT_DIR / clean_session).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = (target_dir / clean_filename).resolve()

        # Path Traversal 방어 검증 (타깃 경로가 OUTPUT_DIR 내부인지 확인)
        if not str(target_path).startswith(str(OUTPUT_DIR)):
            return "[보안 오류] 잘못된 파일 경로 접근이 감지되었습니다."

        if markdown_to_pdf_bytes:
            pdf_data = markdown_to_pdf_bytes(content)
        else:
            raise RuntimeError("PDF 생성 엔진(pdf_generator)을 로드할 수 없습니다.")

        with open(target_path, "wb") as f:
            f.write(pdf_data)

        return f"[성공] 투자 심의 보고서가 PDF 파일('{clean_filename}', 대화방: {clean_session})로 성공적으로 저장되었습니다."
    except Exception as e:
        return f"[오류] PDF 보고서 파일 저장 중 문제가 발생했습니다: {str(e)}"

@mcp.tool("write_markdown", description="[호환용] 보고서를 PDF 파일로 자동 변환하여 저장합니다.")
def write_markdown(filename: str, content: str, session_id: str = "default") -> str:
    """기존 write_markdown 호출 시 자동으로 write_pdf로 연계 처리"""
    return write_pdf(filename, content, session_id)

if __name__ == "__main__":
    mcp.run(transport="stdio")
