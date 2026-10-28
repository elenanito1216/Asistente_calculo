"""
tests/test_app.py - Pruebas automatizadas para el Tutor de Cálculo.

Verifica:
1. Endpoint de salud /api/health
2. Servido de index.html en /
3. Validaciones de esquema en /api/chat (mensajes vacíos, último emisor, límites)
4. Configuración del System Prompt y presencia de las 5 secciones pedagógicas
"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

import app as app_module
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


@pytest.mark.parametrize("resultado, codigo_esperado", [
    ("La derivada de $x^2$ es $2x$.", 200),
    (genai_errors.APIError(429, httpx.Response(429, json={"error": {"message": "RESOURCE_EXHAUSTED"}})), 429),
    (genai_errors.APIError(400, httpx.Response(400, json={"error": {"message": "INVALID_ARGUMENT"}})), 500),
    (genai_errors.APIError(503, httpx.Response(503, json={"error": {"message": "UNAVAILABLE"}})), 503),
    (asyncio.TimeoutError(), 504),
])
def test_chat_con_gemini_simulado(monkeypatch, resultado, codigo_esperado):
    """/api/chat usa el cliente async de Gemini y mapea sus errores al código HTTP correcto."""
    async def generate_content(**kwargs):
        if isinstance(resultado, Exception):
            raise resultado
        return SimpleNamespace(text=resultado)

    cliente_falso = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(app_module, "GEMINI_API_KEY", "clave_falsa")
    monkeypatch.setattr(app_module, "gemini_client", cliente_falso)

    response = client.post("/api/chat", json={"mensajes": [{"rol": "usuario", "contenido": "Deriva x^2"}]})
    assert response.status_code == codigo_esperado
    if codigo_esperado == 200:
        assert response.json()["respuesta"] == resultado


def test_chat_seguimiento_con_respuesta_larga_del_tutor(monkeypatch):
    """Una pregunta de seguimiento no debe fallar si la respuesta previa del tutor supera 3000 caracteres."""
    async def generate_content(**kwargs):
        return SimpleNamespace(text="Detallemos el paso 2...")

    cliente_falso = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(app_module, "GEMINI_API_KEY", "clave_falsa")
    monkeypatch.setattr(app_module, "gemini_client", cliente_falso)

    response = client.post("/api/chat", json={"mensajes": [
        {"rol": "usuario", "contenido": "Integra x e^x"},
        {"rol": "tutor", "contenido": "x" * 5000},
        {"rol": "usuario", "contenido": "Explícame con más detalle el paso 2"},
    ]})
    assert response.status_code == 200


def test_chat_devuelve_verificacion_sympy(monkeypatch):
    """El bloque ```verificacion``` se quita del texto y se devuelve el resultado de SymPy."""
    async def generate_content(**kwargs):
        return SimpleNamespace(text=(
            "La integral es $x e^x - e^x + C$.\n\n```verificacion\n"
            '{"tipo": "integral", "expresion": "x*exp(x)", "variable": "x", "resultado": "x*exp(x) - exp(x)"}\n```'
        ))

    cliente_falso = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(app_module, "GEMINI_API_KEY", "clave_falsa")
    monkeypatch.setattr(app_module, "gemini_client", cliente_falso)

    response = client.post("/api/chat", json={"mensajes": [{"rol": "usuario", "contenido": "Integra x e^x"}]})
    assert response.status_code == 200
    data = response.json()
    assert "```verificacion" not in data["respuesta"]
    assert data["verificacion"] == {"estado": "verificado", "sympy": None}


def test_chat_devuelve_grafica(monkeypatch):
    """El bloque ```grafica``` se quita del texto y se devuelven los puntos calculados."""
    async def generate_content(**kwargs):
        return SimpleNamespace(text='Mira la curva.\n\n```grafica\n{"tipo": "2d", "funciones": ["sin(x)"], "x": [0, 3]}\n```')

    cliente_falso = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(app_module, "GEMINI_API_KEY", "clave_falsa")
    monkeypatch.setattr(app_module, "gemini_client", cliente_falso)

    data = client.post("/api/chat", json={"mensajes": [{"rol": "usuario", "contenido": "Grafica sin(x)"}]}).json()
    assert data["respuesta"] == "Mira la curva."
    assert data["grafica"]["tipo"] == "2d"
    assert len(data["grafica"]["trazos"][0]["x"]) == 300


def test_chat_usa_modelo_de_respaldo_si_el_principal_esta_saturado(monkeypatch):
    """Si el modelo principal responde 503, se reintenta con el siguiente de GEMINI_MODELOS_RESPALDO."""
    usados = []

    async def generate_content(model, **kwargs):
        usados.append(model)
        if model == "principal":
            raise genai_errors.APIError(503, httpx.Response(503, json={"error": {"message": "UNAVAILABLE"}}))
        return SimpleNamespace(text="Respuesta del respaldo.")

    cliente_falso = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(app_module, "GEMINI_API_KEY", "clave_falsa")
    monkeypatch.setattr(app_module, "GEMINI_MODEL", "principal")
    monkeypatch.setenv("GEMINI_MODELOS_RESPALDO", "respaldo1,respaldo2")
    monkeypatch.setattr(app_module, "gemini_client", cliente_falso)

    response = client.post("/api/chat", json={"mensajes": [{"rol": "usuario", "contenido": "Deriva x^2"}]})
    assert response.status_code == 200
    assert response.json()["respuesta"] == "Respuesta del respaldo."
    assert usados == ["principal", "respaldo1"]


def test_chat_devuelve_narracion_validada(monkeypatch):
    """El bloque ```narracion``` se quita del texto; los focos que no son texto se descartan."""
    async def generate_content(**kwargs):
        return SimpleNamespace(text=(
            'Solución.\n\n```narracion\n{"pasos": ['
            '{"texto": "Mira la gráfica.", "foco": "grafica"}, {"texto": "Aplicamos la regla.", "foco": "\\\\frac{d}{dx}"}, '
            '{"texto": "Listo.", "foco": 3}, {"texto": "   "}]}\n```'
        ))

    cliente_falso = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    monkeypatch.setattr(app_module, "GEMINI_API_KEY", "clave_falsa")
    monkeypatch.setattr(app_module, "gemini_client", cliente_falso)

    data = client.post("/api/chat", json={"mensajes": [{"rol": "usuario", "contenido": "Deriva x^2"}]}).json()
    assert data["respuesta"] == "Solución."
    assert data["narracion"] == {"pasos": [
        {"texto": "Mira la gráfica.", "foco": "grafica"},
        {"texto": "Aplicamos la regla.", "foco": "\\frac{d}{dx}"},
        {"texto": "Listo.", "foco": None},
    ]}
