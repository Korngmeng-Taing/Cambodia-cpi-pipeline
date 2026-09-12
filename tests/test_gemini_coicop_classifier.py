import json
from unittest.mock import MagicMock, patch
import pytest

from pipeline.gemini_coicop_classifier import GeminiCOICOPClassifier


@pytest.fixture
def mock_gemini_client():
    with patch("pipeline.gemini_coicop_classifier.genai.Client") as mock_client_cls:
        client = MagicMock()
        mock_client_cls.return_value = client
        yield client


def test_classify_batch_success(mock_gemini_client):
    mock_response = MagicMock()
    mock_response.text = json.dumps([
        {
            "id": "1",
            "coicop_division": "01",
            "coicop_code": "01.1.1",
            "confidence": 0.98,
            "reason": "Human food - rice",
        },
        {
            "id": "2",
            "coicop_division": "09",
            "coicop_code": "09.3.4",
            "confidence": 0.99,
            "reason": "Pet food guardrail",
        },
    ])
    mock_gemini_client.models.generate_content.return_value = mock_response

    classifier = GeminiCOICOPClassifier(db_conn_str="postgresql://localhost:5432/test_db")
    results = classifier._call_gemini_batch([
        {"id": "1", "name": "Jasmine Rice 5kg", "brand": "Angkor"},
        {"id": "2", "name": "Royal Canin Cat Food 2kg", "brand": "Royal Canin"},
    ])

    assert "1" in results
    assert results["1"]["coicop_division"] == "01"
    assert results["1"]["coicop_code"] == "01.1.1"

    assert "2" in results
    assert results["2"]["coicop_division"] == "09"
    assert results["2"]["coicop_code"] == "09.3.4"


def test_classify_single(mock_gemini_client):
    mock_response = MagicMock()
    mock_response.text = json.dumps([
        {
            "id": "0",
            "coicop_division": "02",
            "coicop_code": "02.1.1",
            "confidence": 0.97,
            "reason": "Beer alcohol",
        }
    ])
    mock_gemini_client.models.generate_content.return_value = mock_response

    classifier = GeminiCOICOPClassifier(db_conn_str="postgresql://localhost:5432/test_db")
    res = classifier.classify_single("Angkor Beer Can 330ml", brand="Angkor")

    assert res["coicop_division"] == "02"
    assert res["coicop_code"] == "02.1.1"
