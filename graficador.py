"""
graficador.py - Calcula con SymPy los puntos de las gráficas que se dibujan en la pizarra.

Gemini describe la gráfica en un bloque ```grafica {json}``` (ver prompts.py) y aquí se
evalúa con el mismo parser seguro del verificador. La recta y el plano tangente salen de
derivadas exactas de SymPy, no de la IA. El frontend solo dibuja los puntos con Plotly.

Formatos aceptados:
  2D: {"tipo": "2d", "funciones": ["x^2*sin(x)"], "x": [-5, 5],
       "area": {"funcion": "sin(x)", "desde": "0", "hasta": "pi"},     (opcional)
       "tangente": {"funcion": "x^2", "en": "1"}}                       (opcional)
  3D: {"tipo": "3d", "funcion": "x^2 + y^2", "x": [-2, 2], "y": [-2, 2],
       "plano_tangente": {"en": ["1", "1"]}}                            (opcional)
"""

import math

import sympy

from verificador import _simbolo, parsear

PUNTOS_2D = 300
PUNTOS_3D = 40           # Malla de 40x40 para superficies
MAX_FUNCIONES = 4
MAX_ANCHO_RANGO = 200
LIMITE_VALOR = 1e6       # Valores mayores (asíntotas) se cortan para no aplastar la gráfica

X, Y = _simbolo("x"), _simbolo("y")


def _numero(valor) -> float:
    numero = float(parsear(str(valor)).evalf())
    if not math.isfinite(numero):
        raise ValueError(f"Valor no finito: {valor!r}")
    return numero


def _rango(datos: dict, clave: str) -> tuple[float, float]:
    a, b = (_numero(v) for v in datos.get(clave, [-5, 5]))
    if not 0 < b - a <= MAX_ANCHO_RANGO:
        raise ValueError(f"Rango inválido para {clave}: {a}, {b}")
    return a, b


def _funcion(texto: str, variables: tuple) -> sympy.Expr:
    expr = parsear(texto)
    if not expr.free_symbols <= set(variables):
        raise ValueError(f"La función {texto!r} usa variables fuera de {variables}")
    return expr


def _evaluador(expr: sympy.Expr, variables: tuple):
    f = sympy.lambdify(variables, expr, modules="math")

    def evaluar(*valores):
        # Fuera del dominio (log de negativo, división por cero...) queda un hueco en la curva
        try:
            v = f(*valores)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            return None
        if isinstance(v, complex) or not math.isfinite(v) or abs(v) > LIMITE_VALOR:
            return None
        return float(f"{v:.5g}")  # 5 cifras bastan para dibujar y reducen el tamaño del JSON
    return evaluar


def _malla(a: float, b: float, n: int) -> list[float]:
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def _percentiles(valores: list[float]) -> tuple[float, float]:
    ordenados = sorted(valores)
    return ordenados[int(0.02 * (len(ordenados) - 1))], ordenados[int(0.98 * (len(ordenados) - 1))]


def _cortar_asintotas(ys: list) -> list:
    """Evita la línea vertical falsa en asíntotas (tan, 1/x): corta donde la curva salta de signo."""
    validos = [y for y in ys if y is not None]
    if len(validos) < 2:
        return ys
    bajo, alto = _percentiles(validos)
    umbral = max(alto - bajo, 1e-9)
    cortados = list(ys)
    for i in range(1, len(ys)):
        a, b = ys[i - 1], ys[i]
        if a is not None and b is not None and a * b < 0 and abs(b - a) > umbral:
            cortados[i] = None
    return cortados


def _rango_y(trazos: list[dict]) -> list[float] | None:
    """Si unos pocos valores enormes (cerca de una asíntota) aplastan la gráfica, limita el eje y."""
    valores = [y for t in trazos if t["estilo"] in ("curva", "area") for y in t["y"] if y is not None]
    if len(valores) < 10:
        return None
    bajo, alto = _percentiles(valores)
    if max(valores) - min(valores) <= 3 * max(alto - bajo, 1e-9):
        return None  # Sin valores extremos: el autoescalado de Plotly funciona bien
    margen = 0.15 * (alto - bajo) or 1
    return [bajo - margen, alto + margen]


def _nombre(expr: sympy.Expr) -> str:
    return str(expr).replace("**", "^")


def _grafica_2d(datos: dict) -> dict:
    a, b = _rango(datos, "x")
    xs = _malla(a, b, PUNTOS_2D)
    trazos = []

    for texto in datos.get("funciones", [])[:MAX_FUNCIONES]:
        expr = _funcion(texto, (X,))
        f = _evaluador(expr, (X,))
        trazos.append({"estilo": "curva", "nombre": f"f(x) = {_nombre(expr)}", "x": xs,
                       "y": _cortar_asintotas([f(x) for x in xs])})

    if "area" in datos:
        area = datos["area"]
        expr = _funcion(area["funcion"], (X,))
        desde, hasta = _numero(area["desde"]), _numero(area["hasta"])
        if not a <= desde < hasta <= b:
            raise ValueError("El área debe estar dentro del rango de x.")
        f = _evaluador(expr, (X,))
        xs_area = _malla(desde, hasta, PUNTOS_2D // 2)
        trazos.append({"estilo": "area", "nombre": f"Área entre x = {desde:.3g} y x = {hasta:.3g}",
                       "x": xs_area, "y": [f(x) for x in xs_area]})

    if "tangente" in datos:
        tangente = datos["tangente"]
        expr = _funcion(tangente["funcion"], (X,))
        x0 = _numero(tangente["en"])
        y0 = expr.subs(X, x0).evalf()
        pendiente = sympy.diff(expr, X).subs(X, x0).evalf()
        if not (y0.is_real and pendiente.is_real):
            raise ValueError("La tangente no está definida en ese punto.")
        recta = y0 + pendiente * (X - x0)
        g = _evaluador(recta, (X,))
        trazos.append({"estilo": "tangente", "nombre": f"Recta tangente en x = {x0:.3g} (pendiente {float(pendiente):.4g})",
                       "x": xs, "y": [g(x) for x in xs]})
        trazos.append({"estilo": "punto", "nombre": f"({x0:.3g}, {float(y0):.4g})", "x": [x0], "y": [float(y0)]})

    if not trazos:
        raise ValueError("La gráfica no tiene nada que dibujar.")
    return {"tipo": "2d", "trazos": trazos, "rango_y": _rango_y(trazos)}


def _grafica_3d(datos: dict) -> dict:
    expr = _funcion(datos["funcion"], (X, Y))
    (ax, bx), (ay, by) = _rango(datos, "x"), _rango(datos, "y")
    xs, ys = _malla(ax, bx, PUNTOS_3D), _malla(ay, by, PUNTOS_3D)
    f = _evaluador(expr, (X, Y))
    # Plotly espera z[fila][columna] = f(x[columna], y[fila])
    resultado = {"tipo": "3d", "nombre": f"z = {_nombre(expr)}", "x": xs, "y": ys,
                 "z": [[f(x, y) for x in xs] for y in ys]}

    if "plano_tangente" in datos:
        x0, y0 = (_numero(v) for v in datos["plano_tangente"]["en"])
        punto = {X: x0, Y: y0}
        z0 = expr.subs(punto).evalf()
        fx, fy = sympy.diff(expr, X).subs(punto).evalf(), sympy.diff(expr, Y).subs(punto).evalf()
        if not all(v.is_real for v in (z0, fx, fy)):
            raise ValueError("El plano tangente no está definido en ese punto.")
        plano = _evaluador(z0 + fx * (X - x0) + fy * (Y - y0), (X, Y))
        resultado["plano"] = {"nombre": f"Plano tangente en ({x0:.3g}, {y0:.3g})",
                              "z": [[plano(x, y) for x in xs] for y in ys]}
        resultado["punto"] = {"x": x0, "y": y0, "z": float(z0)}
    return resultado


def generar_grafica(datos: dict) -> dict:
    """Convierte la descripción de Gemini en puntos listos para Plotly. Lanza ValueError si no es válida."""
    if datos.get("tipo") == "2d":
        return _grafica_2d(datos)
    if datos.get("tipo") == "3d":
        return _grafica_3d(datos)
    raise ValueError(f"Tipo de gráfica desconocido: {datos.get('tipo')!r}")
