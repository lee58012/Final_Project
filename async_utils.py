import asyncio
import concurrent.futures
from typing import Any, Coroutine

def run_async_in_isolated_thread(coro_fn, *args, **kwargs) -> Any:
    """
    Streamlit 메인 스레드와 이벤트 루프를 전혀 방해하지 않도록,
    독립된 별도 스레드에서 전용 asyncio 이벤트 루프를 생성하여 실행하고
    작업 완료 즉시 루프를 안전하게 종료(close)합니다.
    
    이 방식을 사용하면 Windows 환경에서 Streamlit의 Ctrl+C 종료 시그널이
    가로채지거나 먹통이 되는 현상을 완벽하게 방지합니다.
    """
    result = None
    exception = None

    def worker():
        nonlocal result, exception
        # 격리된 스레드 전용 새 이벤트 루프
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            coro = coro_fn(*args, **kwargs)
            result = loop.run_until_complete(coro)
        except Exception as e:
            exception = e
        finally:
            try:
                # 남아있는 미완료 태스크 취소 및 정리
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            finally:
                loop.close()
                asyncio.set_event_loop(None)

    # 단일 작업용 스레드에서 실행
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker)
        future.result()  # 스레드 작업 완료 대기

    if exception is not None:
        raise exception

    return result
