# apps/common/runscript_harness.py
import sys, time, traceback

RESULT_PREFIX = "RESULT:"

def _emit(result: str, dur: float | None = None, reason: str = ""):
    parts = [RESULT_PREFIX + result]
    if dur is not None:
        parts.append(f"in {dur:.3f}s")
    if reason:
        parts.append(f"reason={reason}")
    print(" ".join(parts), flush=True)

def binary_harness(fn):
    """
    Décorateur pour un run() de runscript.
    - Exécute fn()
    - Retourne le dict de fn() si présent, sinon un dict standard
    - Écrit une unique ligne RESULT:OK/KO/SKIP lisible par machine
    - N'explose pas le process parent (toujours return 0 côté runscript)
    """
    def _wrapped(*args, **kwargs):
        t0 = time.time()
        try:
            res = fn(*args, **kwargs)
            # tolère run() qui ne renvoie rien: on fabrique un retour OK
            if not isinstance(res, dict):
                res = {"ok": True, "name": fn.__name__, "duration": time.time() - t0, "logs": []}
            ok = bool(res.get("ok", False))
            _emit("OK" if ok else "KO", time.time() - t0)
            return res
        except SystemExit as e:
            code = int(getattr(e, "code", 1) or 0)
            if code == 0:
                _emit("OK", time.time() - t0, "exit=0")
                return {"ok": True, "name": fn.__name__, "duration": time.time() - t0, "logs": ["SystemExit(0)"]}
            _emit("KO", time.time() - t0, f"exit={code}")
            return {"ok": False, "name": fn.__name__, "duration": time.time() - t0, "logs": [f"SystemExit({code})"]}
        except Exception:
            traceback.print_exc()
            _emit("KO", time.time() - t0, "exception")
            return {"ok": False, "name": fn.__name__, "duration": time.time() - t0, "logs": ["exception"]}
    return _wrapped

def skip(reason: str = ""):
    _emit("SKIP", reason=reason)
    return {"ok": True, "name": "skip", "duration": 0.0, "logs": [f"SKIP: {reason}"]}
