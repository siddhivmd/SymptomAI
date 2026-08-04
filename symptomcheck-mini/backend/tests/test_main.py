import os
import sys
import pytest
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Ensure backend path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)

def test_health_check_smoke():
    """Smoke test: GET /health returns HTTP 200 and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

@patch("main.llm_client.generate", new_callable=AsyncMock)
def test_chat_endpoint_smoke_mocked(mock_generate):
    """
    Smoke test: POST /chat returns HTTP 200 and matches ChatOutputPayload schema
    without calling external LLM APIs in CI.
    """
    mock_response = "Hello, what other symptoms are you experiencing?"
    mock_generate.return_value = mock_response

    payload = {
        "arm": "structured",
        "messages": [
            {"role": "patient", "content": "I have a headache."}
        ]
    }

    response = client.post("/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert "complete" in data
    assert "ddx_result" in data
    assert data["message"] == mock_response
    assert data["complete"] is False
    assert mock_generate.called
