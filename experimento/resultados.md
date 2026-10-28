# Resultados del experimento

## Parte 1: Gemini resolviendo ejercicios (gemini-2.5-flash)

| Métrica | Total | Derivadas | Integrales indefinidas | Integrales definidas | Límites |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Ejercicios | 21 | 20 | 1 | 0 | 0 |
| Con bloque de verificación | 100.0% (21/21) | 100.0% (20/20) | 100.0% (1/1) | — | — |
| Exactitud de Gemini | 100.0% (21/21) | 100.0% (20/20) | 100.0% (1/1) | — | — |
| Sello ✅ que eran correctas | 100.0% (21/21) | 100.0% (20/20) | 100.0% (1/1) | — | — |
| Errores detectados con ⚠️ | — | — | — | — | — |
| Sin decidir ❔ | 0.0% (0/21) | 0.0% (0/20) | 0.0% (0/1) | — | — |

### Respuestas incorrectas de Gemini

Ninguna.

## Parte 2: errores sembrados (prueba del detector, sin API)

Cada clave de respuesta correcta se modificó a propósito (signo cambiado, factor 2, término de más).
Las claves sin modificar miden las falsas alarmas.

| Métrica | Total | Derivadas | Integrales indefinidas | Integrales definidas | Límites |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Ejercicios | 312 | 80 | 100 | 56 | 76 |
| Errores detectados con ⚠️ | 99.1% (231/233) | 96.7% (58/60) | 100.0% (75/75) | 100.0% (42/42) | 100.0% (56/56) |
| Sello ✅ que eran correctas | 100.0% (79/79) | 100.0% (20/20) | 100.0% (25/25) | 100.0% (14/14) | 100.0% (20/20) |
| Falsas alarmas ⚠️ en correctas | 0.0% (0/79) | 0.0% (0/20) | 0.0% (0/25) | 0.0% (0/14) | 0.0% (0/20) |
| Sin decidir ❔ | 0.6% (2/312) | 2.5% (2/80) | 0.0% (0/100) | 0.0% (0/56) | 0.0% (0/76) |

### Casos donde el detector no acertó

- **D17** (signo cambiado) `-(sin(x)^cos(x)*(cos(x)^2/sin(x) - sin(x)*log(sin(x))))` · sello: no_verificable
- **D17** (factor 2) `2*(sin(x)^cos(x)*(cos(x)^2/sin(x) - sin(x)*log(sin(x))))` · sello: no_verificable
