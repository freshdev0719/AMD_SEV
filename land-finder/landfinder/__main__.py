"""앱 실행: python -m landfinder [--demo] [--browser]

맥에서는 pywebview로 네이티브 창을 띄우고, 없으면 기본 브라우저로 연다.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn

from .web import create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(prog="landfinder", description="네이버 부동산 단지·매물 찾기")
    parser.add_argument("--demo", action="store_true", help="네이버에 접속하지 않고 가짜 데이터로 실행")
    parser.add_argument("--browser", action="store_true", help="앱 창 대신 기본 브라우저로 열기")
    parser.add_argument("--port", type=int, default=0, help="고정 포트 (기본: 빈 포트 자동 선택)")
    args = parser.parse_args()

    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}/"
    server = uvicorn.Server(uvicorn.Config(create_app(demo=args.demo), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise SystemExit("서버를 시작하지 못했습니다.")
        time.sleep(0.05)

    if not args.browser:
        try:
            import webview  # pywebview
        except ImportError:
            print("pywebview가 없어 브라우저로 엽니다.")
        else:
            webview.create_window("집찾기 – 네이버 부동산 단지·매물", url, width=1440, height=920, min_size=(1000, 640))
            webview.start()
            server.should_exit = True
            return

    print(f"{url} 에서 실행 중입니다. 종료하려면 Ctrl+C")
    webbrowser.open(url)
    try:
        thread.join()
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
