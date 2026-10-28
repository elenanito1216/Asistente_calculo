"""tests/test_graficador.py - Puntos de las gráficas calculados con SymPy."""

import pytest

from graficador import generar_grafica


def test_grafica_2d_con_area_y_tangente():
    g = generar_grafica({"tipo": "2d", "funciones": ["x^2"], "x": [-2, 2],
                         "area": {"funcion": "x^2", "desde": "0", "hasta": "1"},
                         "tangente": {"funcion": "x^2", "en": "1"}})
    estilos = [t["estilo"] for t in g["trazos"]]
    assert estilos == ["curva", "area", "tangente", "punto"]
    tangente = g["trazos"][2]
    # Recta tangente a x^2 en x=1: y = 2x - 1 (pendiente exacta de SymPy)
    assert tangente["y"][0] == pytest.approx(2 * tangente["x"][0] - 1)
    assert g["trazos"][3]["y"] == [1.0]


def test_asintotas_se_cortan():
    ys = generar_grafica({"tipo": "2d", "funciones": ["tan(x)"], "x": [-5, 5]})["trazos"][0]["y"]
    assert sum(y is None for y in ys) == 4  # Asíntotas en ±pi/2 y ±3pi/2


def test_grafica_3d_con_plano_tangente():
    g = generar_grafica({"tipo": "3d", "funcion": "x^2 + y^2", "x": [-2, 2], "y": [-2, 2],
                         "plano_tangente": {"en": ["1", "1"]}})
    assert g["punto"] == {"x": 1.0, "y": 1.0, "z": 2.0}
    # Plano tangente: z = 2 + 2(x-1) + 2(y-1); en la esquina (-2, -2) vale -10
    assert g["plano"]["z"][0][0] == pytest.approx(-10)


@pytest.mark.parametrize("datos", [
    {"tipo": "2d", "funciones": ['__import__("os")']},
    {"tipo": "2d", "funciones": ["x*y"]},
    {"tipo": "2d", "funciones": ["x"], "x": [0, 1e9]},
    {"tipo": "2d", "funciones": ["x"], "area": {"funcion": "x", "desde": "0", "hasta": "oo"}},
    {"tipo": "torta"},
])
def test_rechaza_datos_invalidos(datos):
    with pytest.raises(Exception):
        generar_grafica(datos)
