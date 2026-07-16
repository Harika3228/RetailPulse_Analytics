import argparse
import socket
import sys

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RetailPulse backend in development mode")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--force-reload", action="store_true", help="Force reload even on Windows")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Preferred port")
    return parser.parse_args()


def is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def pick_port(host: str, preferred: int, attempts: int = 20) -> int:
    port = preferred
    for _ in range(attempts):
        if is_port_free(host, port):
            return port
        port += 1
    return preferred


def main() -> None:
    args = parse_args()

    reload_enabled = args.reload or args.force_reload
    if sys.platform.startswith("win") and args.reload and not args.force_reload:
        print("[run_dev] Reload disabled on Windows to avoid SpawnProcess KeyboardInterrupt traces.")
        print("[run_dev] Use --force-reload if you explicitly want reload mode.")
        reload_enabled = False

    selected_port = pick_port(args.host, args.port)
    if selected_port != args.port:
        print(f"[run_dev] Port {args.port} is in use. Falling back to {selected_port}.")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=selected_port,
        reload=reload_enabled,
        lifespan="off",
        log_config=None,
    )


if __name__ == "__main__":
    main()
