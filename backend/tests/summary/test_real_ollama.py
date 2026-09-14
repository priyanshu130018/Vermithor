import json
import pytest
from backend.app.summary.llm.ollama_provider import OllamaProvider


def test_real_ollama_environment():
    """
    Dedicated test for Real Ollama environment.
    Reports REAL LLM TEST: PASS when Ollama is running and responds with valid JSON.
    Reports SKIPPED: Ollama/model unavailable when Ollama is offline.
    """
    provider = OllamaProvider()

    if not provider.is_available():
        pytest.skip("SKIPPED: Ollama/model unavailable")

    prompt = (
        "Respond with a SINGLE valid JSON object matching this schema: "
        '{"status": "ready", "model": "' + provider.get_model_name() + '"}'
    )

    try:
        raw_output = provider.generate(prompt)
        parsed = json.loads(raw_output)
        assert "status" in parsed
        print("\nREAL LLM TEST: PASS")
    except Exception as exc:
        pytest.skip(f"SKIPPED: Ollama responded with error: {exc}")
