import json
import pathlib
import time
import traceback
from datetime import datetime


def _mkdirp(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class Reporter:
    """Collect rich diagnostics for FlowForms E2E runs."""

    def __init__(self, artifacts_dir: pathlib.Path):
        self._t0 = time.time()
        self.artifacts_dir = _mkdirp(artifacts_dir)
        self.screens_dir = _mkdirp(self.artifacts_dir / "screens")
        self.videos_dir = _mkdirp(self.artifacts_dir / "videos")
        self.data = {
            "meta": {
                "started_at": datetime.utcnow().isoformat() + "Z",
                "artifacts_dir": str(self.artifacts_dir),
            },
            "steps": [],
            "warnings": [],
            "errors": [],
            "requests": [],
            "responses": [],
            "console": [],
            "progress_calls": [],
            "config": {},
            "db": {},
        }

    # -------- lifecycle helpers --------
    def step(self, name: str):
        return _StepContext(self, name)

    def note(self, message: str, **extra):
        entry = {"ts": time.time() - self._t0, "note": message}
        if extra:
            entry["extra"] = extra
        self.data["steps"].append(entry)

    def warn(self, message: str, **extra):
        entry = {"ts": time.time() - self._t0, "warning": message}
        if extra:
            entry["extra"] = extra
        self.data["warnings"].append(entry)
        print(f"[WARN] {message}")

    def error(self, message: str, **extra):
        entry = {"ts": time.time() - self._t0, "error": message}
        if extra:
            entry["extra"] = extra
        self.data["errors"].append(entry)
        print(f"[ERR ] {message}")

    # -------- browser hooks --------
    def log_console(self, message, text: str | None = None, args=None):
        # Support both direct ConsoleMessage objects and explicit parameters.
        if hasattr(message, "type") and callable(getattr(message, "type", None)):
            try:
                log_type = message.type
                log_text = message.text
                log_args = [arg.json_value() for arg in message.args] if message.args else None
            except Exception:  # pragma: no cover - defensive
                log_type = str(getattr(message, "type", "console"))
                log_text = str(getattr(message, "text", ""))
                log_args = None
        else:
            log_type = str(message)
            log_text = text or ""
            log_args = args

        payload = {"ts": time.time() - self._t0, "type": log_type, "text": log_text}
        if log_args:
            payload["args"] = log_args
        self.data["console"].append(payload)

    def log_request(self, request):
        try:
            entry = {
                "ts": time.time() - self._t0,
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data or "",
            }
            self.data["requests"].append(entry)
            if request.method == "POST" and "/api/leads/progress/" in request.url:
                self.data["progress_calls"].append(entry)
        except Exception as exc:  # pragma: no cover - defensive
            self.warn("log_request failed", exc=str(exc))

    def log_response(self, response, body_text=None):
        try:
            entry = {
                "ts": time.time() - self._t0,
                "url": response.url,
                "status": response.status,
                "ok": response.ok,
                "headers": dict(response.headers),
            }
            if body_text is not None:
                entry["body_text"] = body_text
            else:
                try:
                    entry["body_json"] = response.json()
                except Exception:
                    entry["body_text"] = response.text()
            self.data["responses"].append(entry)
        except Exception as exc:  # pragma: no cover - defensive
            self.warn("log_response failed", exc=str(exc))

    def screenshot(self, page, label: str) -> str:
        filename = f"{int(time.time() * 1000)}_{label}.png".replace(" ", "_")
        path = self.screens_dir / filename
        try:
            page.screenshot(path=str(path), full_page=True)
            self.note("screenshot", file=str(path))
        except Exception as exc:  # pragma: no cover - best effort
            self.warn("screenshot failed", label=label, exc=str(exc))
        return str(path)

    # -------- finalisation --------
    def finalize(self):
        self.data["meta"]["finished_at"] = datetime.utcnow().isoformat() + "Z"
        self.data["meta"]["duration_sec"] = round(time.time() - self._t0, 3)
        report_path = self.artifacts_dir / "report.json"
        report_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
        print("\n" + "=" * 72)
        print("RAPPORT E2E — Résumé")
        print("=" * 72)
        print(f"Artifacts: {self.artifacts_dir}")
        print(f"- Steps:     {len(self.data['steps'])}")
        print(f"- Requests:  {len(self.data['requests'])} (progress: {len(self.data['progress_calls'])})")
        print(f"- Responses: {len(self.data['responses'])}")
        print(f"- Console:   {len(self.data['console'])}")
        print(f"- Warnings:  {len(self.data['warnings'])}")
        print(f"- Errors:    {len(self.data['errors'])}")
        print("- DB:", json.dumps(self.data.get("db", {}), ensure_ascii=False))
        print("Rapport JSON →", report_path)
        print("=" * 72 + "\n")


class _StepContext:
    def __init__(self, reporter: Reporter, name: str):
        self._reporter = reporter
        self._name = name
        self._t0 = None

    def __enter__(self):
        self._t0 = time.time()
        self._reporter.note(f"BEGIN {self._name}")
        return self

    def __exit__(self, exc_type, exc, tb):
        duration = round(time.time() - (self._t0 or time.time()), 3)
        self._reporter.note(f"END   {self._name}", duration_sec=duration)
        if exc_type:
            stack = "".join(traceback.format_exception(exc_type, exc, tb))
            self._reporter.error(f"Exception in step '{self._name}'", traceback=stack)
        return False
