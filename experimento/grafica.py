"""
experimento/grafica.py - Gráfica para el póster a partir de resultados.json.

Barra apilada al 100% por tipo de ejercicio: qué pasó con cada respuesta del tutor.
Uso: python experimento/grafica.py               ->  experimento/resultados.png
     python experimento/grafica.py --sembrados   ->  experimento/resultados_sembrados.png
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CARPETA = Path(__file__).resolve().parent

# Colores de estado (nunca solo color: cada segmento lleva etiqueta y hay leyenda)
CATEGORIAS = [
    ("Correcta y verificada", "#0ca30c"),
    ("Error detectado por SymPy", "#fab219"),
    ("Falsa alarma (era correcta)", "#ec835a"),
    ("Error NO detectado", "#d03b3b"),
    ("SymPy no pudo decidir", "#c3c2b7"),
    ("Sin bloque de verificación", "#e1e0d9"),
]
TIPOS = [("Total", None), ("Derivadas", "derivada"), ("Integrales\nindefinidas", "integral"),
         ("Integrales\ndefinidas", "integral_definida"), ("Límites", "limite")]
SUPERFICIE, TINTA, TINTA_2, TINTA_MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"


def categoria(r: dict) -> str:
    if r["sello"] == "sin_bloque":
        return "Sin bloque de verificación"
    if r["sello"] == "no_verificable" or r["correcta"] is None:
        return "SymPy no pudo decidir"
    if r["correcta"]:
        return "Correcta y verificada" if r["sello"] == "verificado" else "Falsa alarma (era correcta)"
    return "Error detectado por SymPy" if r["sello"] == "discrepancia" else "Error NO detectado"


def main(sembrados: bool):
    if sembrados:
        resultados = json.loads((CARPETA / "resultados_sembrados.json").read_text(encoding="utf-8"))
        titulo, salida = "¿Detecta SymPy los errores? (respuestas correctas + errores sembrados)", "resultados_sembrados.png"
    else:
        resultados = list(json.loads((CARPETA / "resultados.json").read_text(encoding="utf-8")).values())
        titulo, salida = "¿Qué pasó con cada respuesta del tutor?", "resultados.png"
    filas = [(nombre, [r for r in resultados if tipo is None or r["tipo"] == tipo]) for nombre, tipo in TIPOS]
    filas = [(n, regs) for n, regs in filas if regs]
    usadas = [(c, color) for c, color in CATEGORIAS if any(categoria(r) == c for r in resultados)]

    fig, ax = plt.subplots(figsize=(10, 1.0 + 0.75 * len(filas)), dpi=200)
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)

    for y, (nombre, regs) in enumerate(reversed(filas)):
        izquierda = 0.0
        for cat, color in usadas:
            n = sum(categoria(r) == cat for r in regs)
            if not n:
                continue
            ancho = 100 * n / len(regs)
            # Borde del color de la superficie = separación de 2px entre segmentos
            ax.barh(y, ancho, left=izquierda, height=0.6, color=color, edgecolor=SUPERFICIE, linewidth=2)
            if ancho >= 7:  # Etiqueta directa solo si cabe
                ax.text(izquierda + ancho / 2, y, str(n), ha="center", va="center", fontsize=9,
                        color=TINTA, fontweight="bold")
            izquierda += ancho
        ax.text(101, y, f"n = {len(regs)}", va="center", fontsize=9, color=TINTA_2)

    ax.set_yticks(range(len(filas)), [n for n, _ in reversed(filas)], fontsize=10, color=TINTA)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"], fontsize=9, color=TINTA_MUTED)
    ax.tick_params(length=0)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")

    ax.set_title(titulo, loc="left", fontsize=13,
                 color=TINTA, fontweight="bold", pad=34)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for _, c in usadas], labels=[c for c, _ in usadas],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=9,
              labelcolor=TINTA_2, handlelength=1.2)

    fig.tight_layout()
    fig.savefig(CARPETA / salida, facecolor=SUPERFICIE)
    print(f"Gráfica guardada en {CARPETA / salida}")


if __name__ == "__main__":
    main(sembrados="--sembrados" in sys.argv)
