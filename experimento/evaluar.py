"""
experimento/evaluar.py - Mide qué tan confiable es el tutor y su verificación con SymPy.

Para cada ejercicio de ejercicios.json:
  1. Se le pide a Gemini (con el mismo system prompt de la app) que lo resuelva.
  2. Sello: lo que vería el estudiante, es decir, verificar() sobre el bloque que escribió Gemini.
  3. Corrección real: verificar() con el enunciado ORIGINAL del banco y el resultado de Gemini.
     Las claves de respuesta del banco se validan en tests/test_experimento.py.

Uso (desde la raíz del proyecto):
    python experimento/evaluar.py            # corre lo que falte (se puede interrumpir y retomar)
    python experimento/evaluar.py --n 3      # prueba rápida con 3 ejercicios
    python experimento/evaluar.py --resumen  # solo recalcula la tabla de resultados
    python experimento/evaluar.py --sembrados  # prueba del detector con errores sembrados (sin API)
"""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import sympy
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT
from verificador import extraer_bloque, parsear, verificar

CARPETA = Path(__file__).resolve().parent
ARCHIVO_EJERCICIOS = CARPETA / "ejercicios.json"
ARCHIVO_RESULTADOS = CARPETA / "resultados.json"
ARCHIVO_TABLA = CARPETA / "resultados.md"
ARCHIVO_SEMBRADOS = CARPETA / "resultados_sembrados.json"

PAUSA_SEGUNDOS = 7        # Cuota gratuita de Gemini: ~10 peticiones por minuto
TIMEOUT_SYMPY = 20        # Segundos máximos por comprobación simbólica
NOMBRES_TIPO = {
    "derivada": "Derivadas",
    "integral": "Integrales indefinidas",
    "integral_definida": "Integrales definidas",
    "limite": "Límites",
}


def enunciado(ej: dict) -> str:
    """Redacta el ejercicio como lo escribiría un estudiante, con LaTeX generado por SymPy."""
    f = sympy.latex(parsear(ej["expresion"]))
    v = ej.get("variable", "x")
    if ej["tipo"] == "derivada":
        orden = ej.get("orden", 1)
        if len(parsear(ej["expresion"]).free_symbols) > 1:
            return f"Calcula la derivada parcial $\\frac{{\\partial f}}{{\\partial {v}}}$ de $f = {f}$."
        if orden == 1:
            return f"Calcula la derivada de $f({v}) = {f}$."
        return f"Calcula la derivada de orden {orden} de $f({v}) = {f}$."
    if ej["tipo"] == "integral":
        return f"Calcula la integral $\\int {f} \\, d{v}$."
    if ej["tipo"] == "integral_definida":
        a = sympy.latex(parsear(ej["limite_inferior"]))
        b = sympy.latex(parsear(ej["limite_superior"]))
        return f"Calcula la integral $\\int_{{{a}}}^{{{b}}} {f} \\, d{v}$."
    p = sympy.latex(parsear(ej["punto"]))
    return f"Calcula el límite $\\lim_{{{v} \\to {p}}} {f}$."


def con_timeout(datos: dict) -> str:
    """verificar() con límite de tiempo. Devuelve el estado o 'no_verificable'."""
    salida = {}

    def correr():
        try:
            salida["estado"] = verificar(datos)["estado"]
        except Exception:
            salida["estado"] = "no_verificable"

    # ponytail: hilo daemon que no se puede cancelar; si SymPy se cuelga, sigue hasta que termine el script
    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    hilo.join(TIMEOUT_SYMPY)
    return salida.get("estado", "no_verificable")


def preguntar_a_gemini(cliente, modelo: str, texto: str) -> str:
    from google.genai import errors, types

    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.2)
    for intento in range(5):
        try:
            return cliente.models.generate_content(model=modelo, contents=texto, config=config).text or ""
        except errors.APIError as exc:
            if exc.code == 429 and "PerDay" in str(exc):
                # Esperar un minuto no sirve con la cuota diaria; el progreso ya está guardado
                sys.exit("Se agotó la cuota diaria de Gemini. Vuelve a ejecutar el script mañana: retoma donde quedó.")
            if exc.code not in (429, 500, 503) or intento == 4:
                raise
            print(f"    Gemini respondió {exc.code}; esperando 60 s...")
            time.sleep(60)


def evaluar(ej: dict, respuesta: str) -> dict:
    _, bloque = extraer_bloque(respuesta)
    registro = {"id": ej["id"], "tipo": ej["tipo"], "enunciado": enunciado(ej), "respuesta_tutor": respuesta,
                "bloque": bloque, "sello": "sin_bloque", "correcta": None}
    if bloque is None or "resultado" not in bloque:
        return registro
    registro["sello"] = con_timeout(bloque)
    calificacion = con_timeout({**ej, "resultado": bloque["resultado"]})
    registro["correcta"] = {"verificado": True, "discrepancia": False}.get(calificacion)
    return registro


def correr(n: int | None):
    from google import genai

    load_dotenv(RAIZ / ".env")
    modelo = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
    cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())

    ejercicios = json.loads(ARCHIVO_EJERCICIOS.read_text(encoding="utf-8"))
    resultados = json.loads(ARCHIVO_RESULTADOS.read_text(encoding="utf-8")) if ARCHIVO_RESULTADOS.exists() else {}
    otros_modelos = {r.get("modelo") for r in resultados.values()} - {modelo}
    if otros_modelos:
        sys.exit(f"resultados.json tiene ejercicios evaluados con {', '.join(otros_modelos)} y GEMINI_MODEL es {modelo}.\n"
                 "Mezclar modelos invalida la comparación: renombra resultados.json para empezar de cero con este modelo.")
    pendientes = [e for e in ejercicios if e["id"] not in resultados][:n]
    print(f"Modelo: {modelo} | ya evaluados: {len(resultados)} | pendientes en esta corrida: {len(pendientes)}")

    for i, ej in enumerate(pendientes, 1):
        respuesta = preguntar_a_gemini(cliente, modelo, enunciado(ej))
        registro = evaluar(ej, respuesta)
        registro["modelo"] = modelo
        resultados[ej["id"]] = registro
        # Guardar tras cada ejercicio para poder retomar si se corta
        ARCHIVO_RESULTADOS.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{i}/{len(pendientes)}] {ej['id']}: sello={registro['sello']} correcta={registro['correcta']}")
        time.sleep(PAUSA_SEGUNDOS)


def porcentaje(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}% ({a}/{b})" if b else "—"


def metricas(registros: list[dict]) -> dict:
    con_bloque = [r for r in registros if r["sello"] != "sin_bloque"]
    calificadas = [r for r in con_bloque if r["correcta"] is not None]
    correctas = [r for r in calificadas if r["correcta"]]
    incorrectas = [r for r in calificadas if not r["correcta"]]
    con_check = [r for r in calificadas if r["sello"] == "verificado"]
    return {
        "Ejercicios": str(len(registros)),
        "Con bloque de verificación": porcentaje(len(con_bloque), len(registros)),
        "Exactitud de Gemini": porcentaje(len(correctas), len(calificadas)),
        "Sello ✅ que eran correctas": porcentaje(sum(r["correcta"] for r in con_check), len(con_check)),
        "Errores detectados con ⚠️": porcentaje(sum(r["sello"] == "discrepancia" for r in incorrectas), len(incorrectas)),
        "Falsas alarmas ⚠️ en correctas": porcentaje(sum(r["sello"] == "discrepancia" for r in correctas), len(correctas)),
        "Sin decidir ❔": porcentaje(sum(r["sello"] == "no_verificable" for r in con_bloque), len(con_bloque)),
    }


def sembrar_errores():
    """
    Prueba sin API: a cada clave de respuesta (correcta) se le aplican errores deliberados y se
    mide si verificar() los detecta. Las claves sin modificar miden las falsas alarmas.
    """
    registros = []
    for ej in json.loads(ARCHIVO_EJERCICIOS.read_text(encoding="utf-8")):
        clave = ej["respuesta"]
        # En una integral indefinida sumar una constante no es error; se suma la variable
        extra = ej.get("variable", "x") if ej["tipo"] in ("derivada", "integral") else "1"
        variantes = [("correcta", clave, True), ("signo cambiado", f"-({clave})", False),
                     ("factor 2", f"2*({clave})", False), ("término de más", f"({clave}) + {extra}", False)]
        for mutacion, resultado, es_correcta in variantes:
            # Si el error no cambia el valor (ej. -0 = 0), no es un error real: se descarta
            if not es_correcta and sympy.simplify(parsear(resultado) - parsear(clave)) == 0:
                continue
            registros.append({"id": ej["id"], "tipo": ej["tipo"], "enunciado": enunciado(ej), "mutacion": mutacion,
                              "bloque": {"resultado": resultado}, "correcta": es_correcta,
                              "sello": con_timeout({**ej, "resultado": resultado})})
    ARCHIVO_SEMBRADOS.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")


def tabla_md(registros: list[dict], filas: list[str]) -> list[str]:
    columnas = {"Total": registros}
    for tipo, nombre in NOMBRES_TIPO.items():
        columnas[nombre] = [r for r in registros if r["tipo"] == tipo]
    tabla = {nombre: metricas(regs) for nombre, regs in columnas.items()}
    md = ["| Métrica | " + " | ".join(tabla) + " |", "| :--- |" + " :---: |" * len(tabla)]
    return md + [f"| {f} | " + " | ".join(t[f] for t in tabla.values()) + " |" for f in filas]


def resumen():
    resultados = list(json.loads(ARCHIVO_RESULTADOS.read_text(encoding="utf-8")).values())
    modelos = sorted({r.get("modelo", "?") for r in resultados})
    md = [f"# Resultados del experimento", "", f"## Parte 1: Gemini resolviendo ejercicios ({', '.join(modelos)})", ""]
    md += tabla_md(resultados, ["Ejercicios", "Con bloque de verificación", "Exactitud de Gemini",
                                "Sello ✅ que eran correctas", "Errores detectados con ⚠️", "Sin decidir ❔"])

    errores = [r for r in resultados if r["correcta"] is False]
    md += ["", "### Respuestas incorrectas de Gemini", ""]
    md += [f"- **{r['id']}** {r['enunciado']} → Gemini: `{r['bloque']['resultado']}` · sello: {r['sello']}" for r in errores] or ["Ninguna."]

    if ARCHIVO_SEMBRADOS.exists():
        sembrados = json.loads(ARCHIVO_SEMBRADOS.read_text(encoding="utf-8"))
        md += ["", "## Parte 2: errores sembrados (prueba del detector, sin API)", "",
               "Cada clave de respuesta correcta se modificó a propósito (signo cambiado, factor 2, término de más).",
               "Las claves sin modificar miden las falsas alarmas.", ""]
        md += tabla_md(sembrados, ["Ejercicios", "Errores detectados con ⚠️", "Sello ✅ que eran correctas",
                                   "Falsas alarmas ⚠️ en correctas", "Sin decidir ❔"])
        fallos = [r for r in sembrados if r["sello"] != ("verificado" if r["correcta"] else "discrepancia")]
        md += ["", "### Casos donde el detector no acertó", ""]
        md += [f"- **{r['id']}** ({r['mutacion']}) `{r['bloque']['resultado']}` · sello: {r['sello']}" for r in fallos] or ["Ninguno."]

    texto = "\n".join(md) + "\n"
    ARCHIVO_TABLA.write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, help="evaluar solo N ejercicios pendientes")
    parser.add_argument("--resumen", action="store_true", help="solo regenerar la tabla")
    parser.add_argument("--sembrados", action="store_true", help="prueba de errores sembrados (sin API)")
    args = parser.parse_args()
    if args.sembrados:
        sembrar_errores()
    elif not args.resumen:
        correr(args.n)
    resumen()
