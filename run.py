#!/usr/bin/env python3
"""
Signal Scanner - Unified System Orchestrator (Satu Pintu)
Runs FastAPI Backend, Collector Daemon, and Next.js Frontend simultaneously.
Provides dependency-ordered startup, unified labeled logging, and clean Windows teardown.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Dict, List, Optional

# Enable Windows ANSI Virtual Terminal Colors
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        os.system("")

# ANSI Color Codes
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_CYAN = "\033[96m"
CLR_GREEN = "\033[92m"
CLR_YELLOW = "\033[93m"
CLR_MAGENTA = "\033[95m"
CLR_RED = "\033[91m"
CLR_DIM = "\033[2m"

BANNER = f"""{CLR_CYAN}{CLR_BOLD}
======================================================================
     PEMINDAI AREA - SIGNAL SCANNER UNIFIED RUNNER
     Backend (FastAPI) | Collector (Daemon) | Frontend (Next.js)
======================================================================{CLR_RESET}
"""

processes: List[subprocess.Popen] = []
shutdown_event = threading.Event()


def log(prefix: str, color: str, message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"{CLR_DIM}{timestamp}{CLR_RESET} {color}{CLR_BOLD}[{prefix}]{CLR_RESET} {message}", flush=True)


def stream_reader(proc: subprocess.Popen, prefix: str, color: str) -> None:
    """Reads stdout of a subprocess line-by-line and prints with a prefix."""
    try:
        if proc.stdout:
            for line in iter(proc.stdout.readline, b""):
                if shutdown_event.is_set():
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    log(prefix, color, text)
    except Exception:
        pass


def kill_process_tree(pid: int) -> None:
    """Forcefully kills a process and all its children across Windows/Unix."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            import psutil  # type: ignore
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass


def cleanup() -> None:
    """Terminates all registered child processes."""
    if not processes:
        return
    log("ORCHESTRATOR", CLR_MAGENTA, "Shutting down all components...")
    shutdown_event.set()
    for proc in processes:
        if proc.poll() is None:
            try:
                kill_process_tree(proc.pid)
            except Exception:
                pass
    processes.clear()
    log("ORCHESTRATOR", CLR_MAGENTA, "All services stopped cleanly. Goodbye!")


def handle_exit(signum, frame) -> None:
    cleanup()
    sys.exit(0)


def wait_for_http(url: str, timeout_sec: float = 30.0, step_sec: float = 0.5) -> bool:
    """Polls an HTTP endpoint until it returns a 2xx or 3xx status code."""
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        if shutdown_event.is_set():
            return False
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SignalScanner-Orchestrator"})
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if 200 <= response.status < 400:
                    return True
        except Exception:
            pass
        time.sleep(step_sec)
    return False


def test_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Tests if a port can be bound without permission errors (WinError 10013) or collisions."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except Exception:
        return False


def resolve_available_port(preferred: int, fallbacks: List[int], name: str, host: str = "127.0.0.1") -> int:
    """Selects preferred port if open, or auto-falls back to alternative open ports."""
    if test_port_available(preferred, host):
        return preferred
    log("ORCHESTRATOR", CLR_YELLOW, f"Port {preferred} for {name} is unavailable (blocked or WinError 10013). Searching fallback...")
    for p in fallbacks:
        if test_port_available(p, host):
            log("ORCHESTRATOR", CLR_GREEN, f"Assigned fallback port {p} for {name}.")
            return p
    for p in range(8500, 9500):
        if p not in fallbacks and test_port_available(p, host):
            log("ORCHESTRATOR", CLR_GREEN, f"Assigned fallback port {p} for {name}.")
            return p
    return preferred


def resolve_frontend_runner(port: int = 3000) -> Optional[List[str]]:
    """Detects available node package manager (pnpm, npm) and passes port."""
    pnpm_cmd = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if pnpm_cmd:
        return [pnpm_cmd, "dev", "-p", str(port)]
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_cmd:
        return [npm_cmd, "run", "dev", "--", "-p", str(port)]
    return None


def main() -> None:
    print(BANNER)

    parser = argparse.ArgumentParser(
        description="Signal Scanner - Unified Orchestrator for Backend, Frontend, and Collector",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["wifi", "bluetooth", "radio"],
        default="wifi",
        help="Scanning mode for the collector daemon",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run collector with virtual signal simulator (zero-hardware required)",
    )
    parser.add_argument(
        "--no-collector",
        action="store_true",
        help="Do not start the collector daemon (backend & frontend only)",
    )
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="Do not start the Next.js frontend (backend & collector only)",
    )
    parser.add_argument(
        "--no-backend",
        action="store_true",
        help="Do not start the FastAPI backend",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not automatically open the web browser on launch",
    )
    parser.add_argument(
        "--port-backend",
        type=int,
        default=8000,
        help="Port for FastAPI backend server",
    )
    parser.add_argument(
        "--port-frontend",
        type=int,
        default=3000,
        help="Port for Next.js web application",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=500,
        help="Collector sampling interval in milliseconds",
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Run collector in standalone mode (auto-creates scan session)",
    )

    args = parser.parse_args()

    # Register exit signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    backend_dir = os.path.join(root_dir, "backend")

    # Smart port detection (handles Windows Hyper-V / WSL2 port exclusions)
    backend_port = resolve_available_port(
        preferred=args.port_backend,
        fallbacks=[8888, 9000, 8500, 8081, 8089],
        name="Backend",
    )
    collector_port = resolve_available_port(
        preferred=8001,
        fallbacks=[8889, 9001, 8501, 8082],
        name="Collector Local Agent",
    )
    frontend_port = resolve_available_port(
        preferred=args.port_frontend,
        fallbacks=[3000, 3001, 3002, 3003],
        name="Frontend",
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["FORCE_COLOR"] = "1"
    env["PORT"] = str(frontend_port)
    env["LOCAL_AGENT_PORT"] = str(collector_port)
    env["COLLECTOR_PORT"] = str(collector_port)

    backend_url = f"http://127.0.0.1:{backend_port}"
    collector_url = f"http://127.0.0.1:{collector_port}"

    env["NEXT_PUBLIC_API_URL"] = backend_url
    env["INTERNAL_API_URL"] = backend_url
    env["NEXT_PUBLIC_COLLECTOR_URL"] = collector_url
    env.setdefault("NEXT_PUBLIC_API_AUTH_TOKEN", env.get("API_AUTH_TOKEN", "signal-scanner-dev-token-2026"))
    env.setdefault("NEXT_PUBLIC_LOCAL_COLLECTOR_TOKEN", env.get("LOCAL_AGENT_TOKEN", "signal-scanner-local-agent-token-2026"))

    backend_proc: Optional[subprocess.Popen] = None

    # 1. Launch Backend
    if not args.no_backend:
        log("ORCHESTRATOR", CLR_MAGENTA, f"Launching Backend on {backend_url}...")
        backend_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            "backend",
            "--host",
            "127.0.0.1",
            "--port",
            str(backend_port),
            "--reload",
            "--reload-dir",
            os.path.join(root_dir, "backend"),
        ]
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        processes.append(backend_proc)
        threading.Thread(
            target=stream_reader,
            args=(backend_proc, "BACKEND", CLR_CYAN),
            daemon=True,
        ).start()

        # Wait for Backend to become healthy
        log("ORCHESTRATOR", CLR_MAGENTA, f"Waiting for Backend health check ({backend_url}/healthz)...")
        if wait_for_http(f"{backend_url}/healthz", timeout_sec=20.0):
            log("ORCHESTRATOR", CLR_GREEN, "Backend is HEALTHY and ready!")
        else:
            log("ORCHESTRATOR", CLR_RED, "Backend health check timed out. Proceeding anyway...")
    else:
        log("ORCHESTRATOR", CLR_YELLOW, "Skipping Backend (--no-backend specified)")

    # 2. Launch Collector Daemon
    if not args.no_collector:
        mode_desc = f"{args.mode.upper()} {'(Virtual Mock)' if args.mock else '(Hardware Native)'}"
        log("ORCHESTRATOR", CLR_MAGENTA, f"Launching Collector Daemon [{mode_desc}] on local port {collector_port}...")
        collector_cmd = [
            sys.executable,
            "-m",
            "collector.app.main",
            "--mode",
            args.mode,
            "--backend-url",
            backend_url,
            "--interval",
            str(args.interval),
        ]
        if args.mock:
            collector_cmd.append("--mock")
        if args.standalone:
            collector_cmd.append("--standalone")

        collector_proc = subprocess.Popen(
            collector_cmd,
            cwd=root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        processes.append(collector_proc)
        threading.Thread(
            target=stream_reader,
            args=(collector_proc, "COLLECTOR", CLR_YELLOW),
            daemon=True,
        ).start()
    else:
        log("ORCHESTRATOR", CLR_YELLOW, "Skipping Collector (--no-collector specified)")

    # 3. Launch Frontend
    frontend_url = f"http://localhost:{frontend_port}"
    if not args.no_frontend:
        frontend_runner = resolve_frontend_runner(frontend_port)
        if not frontend_runner:
            log("ORCHESTRATOR", CLR_RED, "Neither 'pnpm' nor 'npm' found in PATH. Skipping Frontend.")
        else:
            # Self-heal check for Windows: make sure node_modules and next binary exist
            next_bin = os.path.join(frontend_dir, "node_modules", ".bin", "next.cmd" if sys.platform == "win32" else "next")
            if not os.path.exists(os.path.join(frontend_dir, "node_modules")) or not os.path.exists(next_bin):
                log("ORCHESTRATOR", CLR_YELLOW, "Frontend node_modules or Next.js shims missing. Auto-running package installation...")
                pkg_cmd = shutil.which("pnpm.cmd") or shutil.which("pnpm") or shutil.which("npm.cmd") or shutil.which("npm")
                if pkg_cmd:
                    install_env = env.copy()
                    install_env["CI"] = "true"
                    res = subprocess.run([pkg_cmd, "install"], cwd=frontend_dir, shell=(sys.platform == "win32"), env=install_env, check=False)
                    if res.returncode != 0:
                        log("ORCHESTRATOR", CLR_RED, f"Package installation failed with exit code {res.returncode}. Continuing anyway...")

            log("ORCHESTRATOR", CLR_MAGENTA, f"Launching Frontend ({' '.join(frontend_runner)}) on {frontend_url}...")
            frontend_proc = subprocess.Popen(
                frontend_runner,
                cwd=frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                shell=(sys.platform == "win32"),
            )
            processes.append(frontend_proc)
            threading.Thread(
                target=stream_reader,
                args=(frontend_proc, "FRONTEND", CLR_GREEN),
                daemon=True,
            ).start()

            # Auto-open browser when frontend is ready
            if not args.no_open:
                def open_browser_when_ready():
                    if wait_for_http(frontend_url, timeout_sec=30.0):
                        log("ORCHESTRATOR", CLR_GREEN, f"Frontend is LIVE! Opening {frontend_url} in your browser...")
                        try:
                            webbrowser.open(frontend_url)
                        except Exception:
                            pass
                threading.Thread(target=open_browser_when_ready, daemon=True).start()
    else:
        log("ORCHESTRATOR", CLR_YELLOW, "Skipping Frontend (--no-frontend specified)")

    # Main monitoring loop
    log("ORCHESTRATOR", CLR_GREEN, f"{CLR_BOLD}All requested services initiated. Press Ctrl+C to stop all services.{CLR_RESET}")
    try:
        monitored_processes = list(processes)
        while not shutdown_event.is_set():
            for proc in list(monitored_processes):
                exit_code = proc.poll()
                if exit_code is not None:
                    monitored_processes.remove(proc)
                    if exit_code != 0 and not shutdown_event.is_set():
                        log("ORCHESTRATOR", CLR_RED, f"A child process (PID {proc.pid}) exited with code {exit_code}")
                        if backend_proc and proc.pid == backend_proc.pid:
                            log("ORCHESTRATOR", CLR_RED, "FastAPI Backend stopped unexpectedly. Shutting down all components...")
                            cleanup()
                            sys.exit(1)
            time.sleep(1.0)
    except KeyboardInterrupt:
        log("ORCHESTRATOR", CLR_MAGENTA, "Received Ctrl+C keyboard interrupt.")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
