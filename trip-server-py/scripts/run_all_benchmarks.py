"""一键启动后端并运行全部基准测试"""
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ["RATE_LIMIT_AUTH_MAX"] = "99999"
os.environ["RATE_LIMIT_AUTH_WINDOW"] = "1"
os.environ["RATE_LIMIT_GLOBAL_MAX"] = "999999"
os.environ["RATE_LIMIT_CHAT_MAX"] = "99999"
os.environ["RATE_LIMIT_RECOMMEND_MAX"] = "99999"

PROJECT_DIR = Path(__file__).resolve().parent.parent  # trip-server-py/
PYTHON = str(PROJECT_DIR / ".venv" / "bin" / "python")


def run(cmd: list[str], desc: str, timeout: int = 300, env: dict | None = None):
    print(f"\n{'='*60}")
    print(f"→ {desc}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True,
                            timeout=timeout, env=env or None)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(f"⚠️  Exit code: {result.returncode}")
    return result.returncode


def main():
    # Step 1: Start backend
    print("Starting backend...")
    backend = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000",
         "--log-level", "error"],
        cwd=PROJECT_DIR,  # 必须在项目根目录运行以找到 src/
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ},
    )
    print(f"Backend PID: {backend.pid}")

    # Wait for backend
    import httpx
    for i in range(15):
        time.sleep(2)
        try:
            r = httpx.post("http://localhost:3000/api/user/login",
                          json={"username": "eval-test", "password": "EvalTest@2026"},
                          timeout=5)
            if r.status_code == 200:
                print(f"Backend ready (attempt {i+1})")
                break
        except Exception:
            pass
        print(f"  waiting... attempt {i+1}")
    else:
        print("Backend failed to start")
        backend.kill()
        sys.exit(1)

    # Step 2: HTTP benchmark
    run([PYTHON, "scripts/benchmark_http.py"], "HTTP Benchmark")

    # Step 3: SSE benchmark (reduced scope for faster runs)
    sse_env = {**os.environ, "SSE_TOTAL_STREAMS": "5", "SSE_CONCURRENCY_LEVELS": "1,5"}
    run([PYTHON, "scripts/benchmark_sse.py"], "SSE Benchmark (5 streams × 1,5 concurrency)", timeout=600, env=sse_env)

    # Step 4: Charts
    run([PYTHON, "-c", """
import sys; sys.path.insert(0, 'scripts')
from benchmark_lib.chart import render_all
render_all()
"""], "Chart Rendering")

    # Step 5: Verify guards
    run([PYTHON, "scripts/verify_guards.py"], "Security Guards")

    # Cleanup
    backend.terminate()
    backend.wait()
    print("\n✅ All benchmarks complete!")


if __name__ == "__main__":
    main()
