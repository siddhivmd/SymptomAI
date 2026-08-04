import pytest
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

def test_health_check():
    """Test health check endpoint returns 200 and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

@patch("backend.main.llm_client.generate", new_callable=AsyncMock)
def test_chat_incomplete_followup(mock_generate):
    """Test POST /chat when model returns a free-text follow-up question (complete=False)."""
    mock_generate.return_value = "Where is your chest pain located, and does it radiate anywhere?"

    payload = {
        "arm": "structured",
        "messages": [
            {"role": "patient", "content": "I have severe chest pain."}
        ]
    }

    response = client.post("/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["complete"] is False
    assert data["ddx_result"] is None
    assert "chest pain" in data["message"]
    assert mock_generate.called

@patch("backend.main.llm_client.generate", new_callable=AsyncMock)
def test_chat_complete_ddx_json(mock_generate):
    """Test POST /chat when model returns valid DDx JSON (complete=True)."""
    ddx_json = {
        "history_summary": "58-year-old male with acute crushing substernal chest pressure.",
        "differential": [
            {"diagnosis": "Acute Myocardial Infarction", "rationale": "Crushing substernal pressure"},
            {"diagnosis": "Aortic Dissection", "rationale": "Severe chest pain"},
            {"diagnosis": "GERD", "rationale": "Retrosternal discomfort"},
            {"diagnosis": "Pericarditis", "rationale": "Pleuritic pain"},
            {"diagnosis": "Costochondritis", "rationale": "Chest wall tenderness"}
        ],
        "disclaimer": "This is an educational demo, not a medical device. It does not provide medical advice. Consult a licensed clinician for any health concern."
    }
    mock_generate.return_value = json.dumps(ddx_json)

    payload = {
        "arm": "dynamic",
        "messages": [
            {"role": "patient", "content": "Chest pain radiating to my arm and sweating."}
        ]
    }

    response = client.post("/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["complete"] is True
    assert data["ddx_result"] is not None
    assert data["ddx_result"]["history_summary"] == ddx_json["history_summary"]
    assert len(data["ddx_result"]["differential"]) == 5
    assert data["ddx_result"]["differential"][0]["diagnosis"] == "Acute Myocardial Infarction"

@patch("backend.main.llm_client.generate", new_callable=AsyncMock)
def test_chat_arm_prompt_selection(mock_generate):
    """Test POST /chat correctly passes selected arm system prompt to GeminiClient."""
    mock_generate.return_value = "Follow up question?"

    for arm in ["base", "structured", "dynamic"]:
        payload = {
            "arm": arm,
            "messages": [{"role": "patient", "content": "Hello"}]
        }
        res = client.post("/chat", json=payload)
        assert res.status_code == 200

    assert mock_generate.call_count == 3
