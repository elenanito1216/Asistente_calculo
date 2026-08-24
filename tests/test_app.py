"""
tests/test_app.py - Pruebas automatizadas para el Tutor de Cálculo.

Verifica:
1. Endpoint de salud /api/health
2. Servido de index.html en /
3. Validaciones de esquema en /api/chat (mensajes vacíos, último emisor, límites)
4. Configuración del System Prompt y presencia de las 5 secciones pedagógicas
"""

import pytest
from fastapi.testclient import TestClient
from app import app
from prompts import SYSTEM_PROMPT


client = TestClient(app)


def test_health_endpoint():
    """El endpoint /api/health debe responder 200 con la estructura esperada."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"
    assert "api_key_configured" in data
    assert "model" in data
    assert "max_history_tokens_limit" in data
    assert data["max_history_tokens_limit"] == 10


def test_root_serves_html():
    """La raíz GET / debe devolver el contenido HTML del frontend."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "AI Tutor" in response.text
    assert "katex" in response.text.lower()


def test_chat_empty_messages_validation():
    """POST /api/chat debe rechazar una lista vacía de mensajes con 422."""
    response = client.post("/api/chat", json={"mensajes": []})
    assert response.status_code == 422


def test_chat_empty_content_validation():
    """POST /api/chat debe rechazar mensajes con solo espacios en blanco con 422."""
    response = client.post("/api/chat", json={
        "mensajes": [
            {"rol": "usuario", "contenido": "   "}
        ]
    })
    assert response.status_code == 422


def test_chat_last_message_must_be_user():
    """POST /api/chat debe rechazar si el último mensaje no es del usuario (estudiante)."""
    response = client.post("/api/chat", json={
        "mensajes": [
            {"rol": "usuario", "contenido": "Deriva x^2"},
            {"rol": "tutor", "contenido": "La derivada es 2x"}
        ]
    })
    assert response.status_code == 422


def test_chat_message_length_limit():
    """POST /api/chat debe rechazar mensajes de más de 3000 caracteres."""
    mensaje_largo = "x" * 3001
    response = client.post("/api/chat", json={
        "mensajes": [
            {"rol": "usuario", "contenido": mensaje_largo}
        ]
    })
    assert response.status_code == 422


def test_system_prompt_pedagogical_structure():
    """El system prompt debe contener las 5 fases pedagógicas requeridas y reglas de KaTeX."""
    assert "1. Identificación" in SYSTEM_PROMPT
    assert "2. Concepto Clave" in SYSTEM_PROMPT or "2. Concepto clave" in SYSTEM_PROMPT.lower()
    assert "3. Desarrollo Paso a Paso" in SYSTEM_PROMPT or "3. Desarrollo paso a paso" in SYSTEM_PROMPT.lower()
    assert "4. Verificación" in SYSTEM_PROMPT
    assert "5. Error Común" in SYSTEM_PROMPT or "5. Error común" in SYSTEM_PROMPT.lower()
    
    # Reglas de KaTeX
    assert "$...$" in SYSTEM_PROMPT or "$" in SYSTEM_PROMPT
    assert "$$" in SYSTEM_PROMPT
    assert "aligned" in SYSTEM_PROMPT
