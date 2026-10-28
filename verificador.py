"""
verificador.py - Verificación simbólica de las respuestas del tutor con SymPy.

La IA propone, SymPy comprueba: Gemini adjunta al final de su respuesta un bloque
```verificacion {json}``` con el resultado final en sintaxis SymPy, y aquí se
comprueba de forma independiente (derivando, integrando numéricamente o
calculando el límite).
"""

import json
import re

import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, convert_xor


# parse_expr usa eval() internamente y el texto viene de la IA (que el estudiante
# puede manipular), así que solo se aceptan caracteres, funciones y símbolos de esta lista.
FUNCIONES = {
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan, "cot": sympy.cot,
    "sec": sympy.sec, "csc": sympy.csc, "asin": sympy.asin, "acos": sympy.acos,
    "atan": sympy.atan, "sinh": sympy.sinh, "cosh": sympy.cosh, "tanh": sympy.tanh,
    "exp": sympy.exp, "log": sympy.log, "ln": sympy.log, "sqrt": sympy.sqrt,
    "abs": sympy.Abs, "Abs": sympy.Abs, "pi": sympy.pi, "e": sympy.E, "E": sympy.E,
    "oo": sympy.oo,
}
SIMBOLOS_LARGOS = {"theta", "phi"}
CARACTERES_PERMITIDOS = re.compile(r"^[0-9A-Za-z+\-*/^()., ]+$")
ACCESO_ATRIBUTO = re.compile(r"[A-Za-z)]\s*\.")
TRANSFORMACIONES = standard_transformations + (convert_xor,)


def _simbolo(nombre: str) -> sympy.Symbol:
    # Variables reales (cálculo universitario): con símbolos complejos, simplificar
    # expresiones con abs(), como log(abs(x+1)), puede tardar minutos.
    return sympy.Symbol(nombre, real=True)


def _es_nombre_permitido(nombre: str) -> bool:
    return nombre in FUNCIONES or nombre in SIMBOLOS_LARGOS or len(nombre) == 1


def parsear(texto: str) -> sympy.Expr:
    """Convierte un string en sintaxis SymPy (ej. 'x*exp(x) - exp(x)') a expresión, de forma segura."""
    texto = str(texto).strip()
    if not texto or len(texto) > 300 or not CARACTERES_PERMITIDOS.match(texto) or ACCESO_ATRIBUTO.search(texto):
        raise ValueError(f"Expresión no permitida: {texto!r}")
    for nombre in re.findall(r"[A-Za-z]+", texto):
        if not _es_nombre_permitido(nombre):
            raise ValueError(f"Nombre no permitido: {nombre!r}")

    # Sin __builtins__, eval no puede alcanzar funciones de Python; solo lo que está aquí.
    entorno = {"__builtins__": {}, "Symbol": _simbolo, "Integer": sympy.Integer,
               "Float": sympy.Float, "Rational": sympy.Rational, **FUNCIONES}
    return parse_expr(texto, global_dict=entorno, transformations=TRANSFORMACIONES)


def _iguales(a, b) -> bool | None:
    """True/False si SymPy puede decidirlo; None si no puede."""
    if a == b:
        return True
    return sympy.simplify(a - b).equals(0)


def verificar(datos: dict) -> dict:
    """
    Comprueba el resultado propuesto por la IA.
    Devuelve {"estado": "verificado" | "discrepancia" | "no_verificable", "sympy": latex | None}.
    """
    tipo = datos.get("tipo")
    variable = str(datos.get("variable", "x"))
    if not _es_nombre_permitido(variable) or not variable.isalpha() or variable in FUNCIONES:
        raise ValueError(f"Variable no permitida: {variable!r}")
    var = _simbolo(variable)
    expr = parsear(datos["expresion"])
    # La constante de integración no afecta la comprobación
    resultado = parsear(datos["resultado"]).subs(_simbolo("C"), 0)

    if tipo == "derivada":
        orden = int(datos.get("orden", 1))
        if not 1 <= orden <= 4:
            raise ValueError("Orden de derivada fuera de rango.")
        esperado = sympy.diff(expr, var, orden)
        ok = _iguales(esperado, resultado)
    elif tipo == "integral":
        # d/dx ln|u| = d/dx ln(u) = u'/u, pero SymPy no simplifica bien sign(u)/|u|
        resultado = resultado.replace(
            lambda e: e.func == sympy.log and isinstance(e.args[0], sympy.Abs),
            lambda e: sympy.log(e.args[0].args[0]),
        )
        # Una antiderivada es correcta si al derivarla se recupera el integrando
        esperado = sympy.diff(resultado, var)
        ok = _iguales(esperado, expr)
        esperado = None  # Mostrar la derivada no ayuda; el estudiante ve solo el sello
    elif tipo == "integral_definida":
        a, b = parsear(datos["limite_inferior"]), parsear(datos["limite_superior"])
        esperado = sympy.Integral(expr, (var, a, b)).evalf()
        valor = resultado.evalf()
        if not (esperado.is_number and valor.is_number):
            ok = None
        else:
            ok = abs(esperado - valor) <= 1e-6 * max(1, abs(esperado))
        if not ok:
            # La integración numérica pierde precisión en integrales impropias que decaen
            # lento (ej. 1/(x ln²x) en [e, ∞) da 0.9958); antes de marcar error, probar la exacta.
            exacto = sympy.integrate(expr, (var, a, b))
            if not exacto.has(sympy.Integral):
                esperado = exacto
                ok = _iguales(exacto, resultado)
    elif tipo == "limite":
        esperado = sympy.limit(expr, var, parsear(datos["punto"]))
        ok = _iguales(esperado, resultado)
    else:
        raise ValueError(f"Tipo de verificación desconocido: {tipo!r}")

    if ok is None:
        return {"estado": "no_verificable", "sympy": None}
    return {
        "estado": "verificado" if ok else "discrepancia",
        "sympy": None if ok or esperado is None else sympy.latex(esperado),
    }


def extraer_bloque(respuesta: str, nombre: str = "verificacion") -> tuple[str, dict | None]:
    """Separa el bloque ```<nombre> {json}``` que Gemini agrega al final (ver prompts.py).
    Devuelve (texto_limpio, datos | None)."""
    patron = re.compile(rf"```{nombre}\s*(\{{.*?\}})\s*```", re.DOTALL)
    coincidencia = patron.search(respuesta)
    if not coincidencia:
        return respuesta, None
    texto = patron.sub("", respuesta).rstrip()
    try:
        return texto, json.loads(coincidencia.group(1))
    except json.JSONDecodeError:
        return texto, None
