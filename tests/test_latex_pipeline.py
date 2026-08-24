"""
Test de verificación del pipeline de placeholders para los 6 casos críticos.
"""
import re

casos = [
    # 1. Integral definida con límites
    r"La integral es $\int_{0}^{\pi} \sin(x)\,dx = 2$.",
    # 2. Fracción con derivadas parciales
    r"Calculamos la derivada parcial cruzada: $$\frac{\partial^2 f}{\partial x \partial y}$$",
    # 3. Límite
    r"El límite fundamental es $\lim_{x \to 0} \frac{\sin x}{x} = 1$.",
    # 4. Display largo con aligned
    r"""El gradiente viene dado por:
$$
\begin{aligned}
\nabla f(x,y) &= \left( \frac{\partial f}{\partial x}, \frac{\partial f}{\partial y} \right) \\
&= (2x\cos(y), -x^2\sin(y))
\end{aligned}
$$""",
    # 5. Negrita junto a fórmula
    r"**Paso 1:** Calculamos $\frac{df}{dx}$ usando la regla de la cadena.",
    # 6. Lista numerada con LaTeX en cada ítem
    """1. Primer paso: evaluamos $f(0) = 1$.
2. Segundo paso: derivamos $f'(x) = 2x$."""
]

for idx, caso in enumerate(casos, 1):
    math_blocks = []

    def replace_display(match):
        ph = f"%%KATEX_DISPLAY_{len(math_blocks)}%%"
        math_blocks.append(("display", match.group(1).strip()))
        return ph

    def replace_inline(match):
        ph = f"%%KATEX_INLINE_{len(math_blocks)}%%"
        math_blocks.append(("inline", match.group(1).strip()))
        return ph

    step1 = re.sub(r"\$\$([\s\S]+?)\$\$", replace_display, caso)
    step2 = re.sub(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", replace_inline, step1)
    
    # Simular que el texto pasa por markdown y luego se reinyecta
    reinyectado = step2
    for b_idx, (b_type, b_content) in enumerate(math_blocks):
        if b_type == "display":
            reinyectado = reinyectado.replace(f"%%KATEX_DISPLAY_{b_idx}%%", f"$${b_content}$$")
        else:
            reinyectado = reinyectado.replace(f"%%KATEX_INLINE_{b_idx}%%", f"${b_content}$")
    
    print(f"--- Caso {idx} ---")
    print("Original:\n", caso)
    print("Reinyectado:\n", reinyectado)
    assert len(math_blocks) > 0
    print("-> OK!\n")

print("TODOS LOS CASOS PROBADOS CON ÉXITO")
