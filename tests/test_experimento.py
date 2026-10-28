"""tests/test_experimento.py - Las claves de respuesta del banco de ejercicios deben ser correctas según SymPy."""

import json
from pathlib import Path

import pytest

from verificador import verificar

EJERCICIOS = json.loads((Path(__file__).parent.parent / "experimento" / "ejercicios.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("ejercicio", EJERCICIOS, ids=[e["id"] for e in EJERCICIOS])
def test_clave_de_respuesta_correcta(ejercicio):
    assert verificar({**ejercicio, "resultado": ejercicio["respuesta"]})["estado"] == "verificado"
