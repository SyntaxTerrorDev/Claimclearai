"""Model fallback: a slow or busy Gemini model must be skipped at once, not retried (no network used)."""
import llm_extract


class _Passthrough:
    """Stands in for the pydantic schema so the test can return a minimal dict."""
    def __init__(self, **kw): self._kw = kw
    def model_dump(self): return self._kw


def _run_with(monkeypatch, failures):
    calls = []

    def fake_gemini(prompt, model):
        calls.append(model)
        if model in failures:
            raise RuntimeError(failures[model])
        return {"discharge_summary": {}, "claim_part_b": {}}

    monkeypatch.setattr(llm_extract, "GEMINI_MODELS", ["slow-model", "fast-model"])
    monkeypatch.setattr(llm_extract, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(llm_extract, "_call_gemini", fake_gemini)
    monkeypatch.setattr(llm_extract, "ExtractionOutput", _Passthrough)
    monkeypatch.setattr(llm_extract.time, "sleep", lambda s: None)
    events = []
    llm_extract.run("clinical", "claim", on_event=lambda k, i=None: events.append((k, i)))
    return calls, events


def test_504_deadline_skips_to_next_model_without_retry(monkeypatch):
    calls, events = _run_with(monkeypatch, {"slow-model": "504 DEADLINE_EXCEEDED. Deadline expired before operation could complete."})
    assert calls == ["slow-model", "fast-model"]          # one attempt only, then the next model
    assert ("llm_fallback", {"from": "Slow Model", "to": "Fast Model", "reason": "timed out"}) in events


def test_503_busy_also_skips(monkeypatch):
    calls, _ = _run_with(monkeypatch, {"slow-model": "503 UNAVAILABLE"})
    assert calls == ["slow-model", "fast-model"]


def test_unknown_error_is_retried_once_on_same_model(monkeypatch):
    calls, _ = _run_with(monkeypatch, {"slow-model": "500 INTERNAL"})
    assert calls == ["slow-model", "slow-model", "fast-model"]


def test_short_reason_labels():
    assert llm_extract._short_reason(Exception("504 DEADLINE_EXCEEDED")) == "timed out"
    assert llm_extract._short_reason(Exception("503 UNAVAILABLE")) == "busy (503)"
    assert llm_extract._short_reason(Exception("429 RESOURCE_EXHAUSTED")) == "rate limited (429)"


def test_flash_lite_is_tried_first_by_default():
    assert llm_extract.GEMINI_MODELS[0] == "gemini-3.5-flash-lite" or llm_extract.os.getenv("GEMINI_MODELS")
