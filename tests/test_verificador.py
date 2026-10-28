"""tests/test_verificador.py - Comprobación simbólica con SymPy y bloqueo de expresiones peligrosas."""

import pytest

from verificador import extraer_bloque, parsear, verificar


@pytest.mark.parametrize("datos, estado", [
    ({"tipo": "integral", "expresion": "x*exp(x)", "resultado": "x*exp(x) - exp(x) + C"}, "verificado"),
    ({"tipo": "integral", "expresion": "x*exp(x)", "resultado": "x*exp(x) + exp(x)"}, "discrepancia"),
    ({"tipo": "derivada", "expresion": "sin(x^2)", "resultado": "2*x*cos(x^2)"}, "verificado"),
    ({"tipo": "derivada", "expresion": "x^2*y^3", "variable": "y", "resultado": "3*x^2*y^2"}, "verificado"),
    ({"tipo": "derivada", "expresion": "x^3", "orden": 2, "resultado": "3*x"}, "discrepancia"),
    ({"tipo": "integral_definida", "expresion": "sin(x)", "limite_inferior": "0",
      "limite_superior": "pi", "resultado": "2"}, "verificado"),
    ({"tipo": "limite", "expresion": "sin(x)/x", "punto": "0", "resultado": "1"}, "verificado"),
    ({"tipo": "limite", "expresion": "(1+1/n)^n", "variable": "n", "punto": "oo", "resultado": "E"}, "verificado"),
])
def test_verificar(datos, estado):
    assert verificar(datos)["estado"] == estado


def test_discrepancia_muestra_valor_de_sympy():
    assert verificar({"tipo": "derivada", "expresion": "x^3", "orden": 2, "resultado": "3*x"})["sympy"] == "6 x"


@pytest.mark.parametrize("malicioso", [
    '__import__("os")', "x.__class__", "open(1)", "Symbol.mro", "(1).real", "lambda: 1", "x[0]",
])
def test_parsear_bloquea_codigo(malicioso):
    with pytest.raises(ValueError):
        parsear(malicioso)


def test_extraer_bloque_quita_el_bloque_del_texto():
    texto, datos = extraer_bloque('Solución.\n\n```verificacion\n{"tipo": "limite", "punto": "0"}\n```')
    assert texto == "Solución."
    assert datos == {"tipo": "limite", "punto": "0"}


@pytest.mark.parametrize("resultado, estado", [
    ("log(abs(x-1))/2 - log(abs(x+1))/2", "verificado"),
    ("log(abs(x-1))/2 + log(abs(x+1))/2", "discrepancia"),
])
def test_integral_con_logaritmo_de_valor_absoluto(resultado, estado):
    """ln|u| no debe colgar SymPy ni dar falsas alarmas."""
    assert verificar({"tipo": "integral", "expresion": "1/(x^2-1)", "resultado": resultado})["estado"] == estado
