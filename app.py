"""
app.py - Servidor Backend para el Tutor Inteligente de Cálculo Universitario.

Construido con FastAPI y el SDK oficial vigente de Google Gemini (google-genai).
Gestiona el ciclo de vida del chat multi-turno, validación de mensajes,
manejo de errores pedagógicos y entrega de archivos estáticos.
"""

import os
import sys
import asyncio
import logging
from typing import List, Literal, Optional
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from google.genai import errors as genai_errors
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

# Cargar variables de entorno desde .env
load_dotenv()

# Configuración del registro de logs en consola
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("tutor_calculo")

# Importar el system prompt pedagógico
try:
    from prompts import SYSTEM_PROMPT
except ImportError:
    logger.error("No se encontró el archivo prompts.py. Asegúrate de que existe en la raíz del proyecto.")
    SYSTEM_PROMPT = "Eres un tutor experto de cálculo universitario."

from verificador import extraer_bloque, verificar
from graficador import generar_grafica

# ============================================================================
# CONFIGURACIÓN Y CLIENTE GEMINI (google-genai)
# ============================================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
PORT = int(os.getenv("PORT", "8000"))

# Límite máximo de mensajes pasados en el historial para controlar consumo de tokens
MAX_HISTORIAL_MENSAJES = 10  # Equivale a 5 intercambios completos estudiante/tutor
TIMEOUT_SEGUNDOS = 45.0      # Límite de tiempo para la generación de la respuesta
TIMEOUT_VERIFICACION = 8.0   # Límite para la comprobación simbólica con SymPy
# Modelos que se prueban en orden si GEMINI_MODEL está saturado (configurable en .env)
MODELOS_RESPALDO_DEFAULT = "gemini-flash-lite-latest,gemini-3.8-flash"


async def verificar_respuesta(texto: str) -> tuple[str, Optional[dict]]:
    """Quita el bloque ```verificacion``` de la respuesta y comprueba el resultado con SymPy."""
    texto, datos = extraer_bloque(texto)
    if datos is None:
        return texto, None
    try:
        # ponytail: el hilo no se puede cancelar; si SymPy se cuelga sigue consumiendo CPU
        # en segundo plano. Usar un proceso aparte si se publica para muchos usuarios.
        return texto, await asyncio.wait_for(asyncio.to_thread(verificar, datos), TIMEOUT_VERIFICACION)
    except Exception as exc:
        logger.warning(f"No se pudo verificar con SymPy ({datos}): {exc!r}")
        return texto, {"estado": "no_verificable", "sympy": None}


def narracion_respuesta(texto: str) -> tuple[str, Optional[dict]]:
    """Quita el bloque ```narracion``` (guion para la voz) y valida su forma."""
    texto, datos = extraer_bloque(texto, "narracion")
    if not isinstance(datos, dict) or not isinstance(datos.get("pasos"), list):
        return texto, None
    pasos = []
    for paso in datos["pasos"][:8]:
        if not isinstance(paso, dict) or not isinstance(paso.get("texto"), str) or not paso["texto"].strip():
            continue
        foco = paso.get("foco")
        # "grafica" o el comienzo del LaTeX de una fórmula $$...$$ (el frontend busca cuál coincide)
        foco = foco.strip()[:200] or None if isinstance(foco, str) else None
        pasos.append({"texto": paso["texto"].strip()[:400], "foco": foco})
    return texto, ({"pasos": pasos} if pasos else None)


async def graficar_respuesta(texto: str) -> tuple[str, Optional[dict]]:
    """Quita el bloque ```grafica``` de la respuesta y calcula sus puntos con SymPy."""
    texto, datos = extraer_bloque(texto, "grafica")
    if datos is None:
        return texto, None
    try:
        return texto, await asyncio.wait_for(asyncio.to_thread(generar_grafica, datos), TIMEOUT_VERIFICACION)
    except Exception as exc:
        # Sin gráfica la respuesta sigue siendo útil; no se muestra error al estudiante
        logger.warning(f"No se pudo generar la gráfica ({datos}): {exc!r}")
        return texto, None

# Cliente global de Gemini
gemini_client = None

def inicializar_cliente_gemini() -> bool:
    """
    Inicializa o actualiza el cliente de Google Gemini usando el SDK oficial google-genai.
    Recarga variables desde .env para permitir cambios sin reiniciar el servidor.
    """
    global gemini_client, GEMINI_API_KEY, GEMINI_MODEL
    
    load_dotenv(override=True)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

    if not GEMINI_API_KEY or GEMINI_API_KEY == "test_key_for_verification":
        logger.error(
            "\n" + "=" * 70 + "\n"
            "❌ ERROR CRÍTICO: No se encontró una GEMINI_API_KEY válida.\n"
            "Para solucionarlo:\n"
            "  1. Abre el archivo .env en la raíz de tu proyecto\n"
            "  2. Obtén tu clave real en https://aistudio.google.com/\n"
            "  3. Coloca tu clave: GEMINI_API_KEY=AIzaSy...\n"
            + "=" * 70 + "\n"
        )
        gemini_client = None
        return False
    
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info(f"Cliente de Gemini inicializado correctamente. Modelo: {GEMINI_MODEL}")
        return True
    except Exception as e:
        logger.error(f"Error al instanciar el cliente de Google Gemini: {e}")
        gemini_client = None
        return False


# Ciclo de vida de la aplicación FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verificación al arranque
    tiene_clave = inicializar_cliente_gemini()
    if not tiene_clave:
        logger.warning("El servidor inició sin GEMINI_API_KEY configurada. Las llamadas a /api/chat fallarán.")
    yield
    # Limpieza al apagar (si fuera necesaria)
    logger.info("Servidor apagándose...")


app = FastAPI(
    title="Tutor Inteligente de Cálculo",
    description="Asistente pedagógico para Cálculo Diferencial, Integral y Multivariado",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware de CORS (habilitado para permitir integración limpia si fuera necesario)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MODELOS DE DATOS (PYDANTIC)
# ============================================================================

class Mensaje(BaseModel):
    rol: Literal["usuario", "tutor"] = Field(
        ..., 
        description="Emisor del mensaje: 'usuario' (estudiante) o 'tutor' (IA)"
    )
    contenido: str = Field(
        ..., 
        min_length=1, 
        max_length=20000,
        description="Texto del mensaje (no vacío; máx 3000 caracteres si es del estudiante)"
    )

    @field_validator("contenido")
    @classmethod
    def validar_contenido_no_blanco(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El mensaje no puede contener únicamente espacios en blanco.")
        return limpio

    # Solo el estudiante tiene límite de 3000: las respuestas del tutor (5 fases) suelen ser
    # más largas y viajan en el historial de cada pregunta de seguimiento.
    @model_validator(mode="after")
    def validar_largo_usuario(self) -> "Mensaje":
        if self.rol == "usuario" and len(self.contenido) > 3000:
            raise ValueError("El mensaje del estudiante no puede superar los 3000 caracteres.")
        return self


class ChatRequest(BaseModel):
    mensajes: List[Mensaje] = Field(
        ..., 
        min_length=1, 
        description="Historial completo de la conversación"
    )

    @field_validator("mensajes")
    @classmethod
    def validar_ultimo_mensaje_usuario(cls, mensajes: List[Mensaje]) -> List[Mensaje]:
        if not mensajes:
            raise ValueError("La lista de mensajes no puede estar vacía.")
        if mensajes[-1].rol != "usuario":
            raise ValueError("El último mensaje de la conversación debe provenir del estudiante ('usuario').")
        return mensajes


class ChatResponse(BaseModel):
    respuesta: str = Field(..., description="Explicación pedagógica en formato Markdown + LaTeX")
    verificacion: Optional[dict] = Field(
        None,
        description="Resultado de la comprobación con SymPy: {estado, sympy}. None si la respuesta no trae resultado verificable."
    )
    grafica: Optional[dict] = Field(
        None,
        description="Puntos calculados con SymPy para dibujar con Plotly (ver graficador.py). None si no hay gráfica."
    )
    narracion: Optional[dict] = Field(
        None,
        description="Guion para la voz: {pasos: [{texto, foco}]}, foco = 'grafica' | comienzo del LaTeX de una fórmula | None."
    )


class HealthResponse(BaseModel):
    status: str
    api_key_configured: bool
    model: str
    max_history_tokens_limit: int


# ============================================================================
# ENDPOINTS DE LA API
# ============================================================================

@app.get("/api/health", response_model=HealthResponse, tags=["Salud y Diagnóstico"])
async def check_health():
    """
    Verifica el estado del servicio y si la API Key de Gemini está configurada.
    """
    return HealthResponse(
        status="ok",
        api_key_configured=bool(GEMINI_API_KEY and gemini_client is not None),
        model=GEMINI_MODEL,
        max_history_tokens_limit=MAX_HISTORIAL_MENSAJES
    )


@app.post("/api/chat", response_model=ChatResponse, tags=["Chat Pedagógico"])
async def chat_calculo(request: ChatRequest):
    """
    Procesa una pregunta o duda de cálculo en el contexto del historial multi-turno.
    Llama al SDK oficial de Google Gemini aplicando el System Prompt pedagógico.
    """
    global gemini_client

    # 1. Validar que la API Key esté disponible
    if not GEMINI_API_KEY or gemini_client is None:
        # Intentar inicializar nuevamente por si fue configurada recientemente
        if not inicializar_cliente_gemini():
            logger.error("Petición rechazada: GEMINI_API_KEY no configurada.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="La clave GEMINI_API_KEY no está configurada en el servidor. Por favor configura el archivo .env."
            )

    # 2. Tomar los últimos N mensajes para limitar el consumo de tokens
    historial_reciente = request.mensajes[-MAX_HISTORIAL_MENSAJES:]
    
    # 3. Construir los objetos types.Content para google-genai
    try:
        from google.genai import types
        
        contents = []
        for msg in historial_reciente:
            # En google-genai, el rol de usuario es 'user' y el del modelo es 'model'
            role = "user" if msg.rol == "usuario" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.contenido)]
                )
            )

        # 4. Configuración de generación pedagógica
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2, # Baja temperatura para alta precisión y rigor algebraico
        )

        # 5. Ejecutar la llamada a Gemini, pasando a un modelo de respaldo si el principal
        #    está saturado (503), sin cuota (429), no existe (404) o no responde a tiempo.
        respaldo = [m.strip() for m in os.getenv("GEMINI_MODELOS_RESPALDO", MODELOS_RESPALDO_DEFAULT).split(",")]
        modelos = [GEMINI_MODEL] + [m for m in respaldo if m and m != GEMINI_MODEL]

        for i, modelo in enumerate(modelos):
            logger.info(f"Enviando consulta a Gemini ({modelo}) con {len(contents)} mensajes en el historial...")
            try:
                # Cliente async (.aio) para no bloquear el event loop mientras Gemini responde
                response = await asyncio.wait_for(
                    gemini_client.aio.models.generate_content(
                        model=modelo,
                        contents=contents,
                        config=config
                    ),
                    timeout=TIMEOUT_SEGUNDOS
                )
                break
            except Exception as exc:
                no_disponible = isinstance(exc, asyncio.TimeoutError) or (
                    isinstance(exc, genai_errors.APIError) and exc.code in (404, 429, 503)
                )
                if not no_disponible or i == len(modelos) - 1:
                    raise
                logger.warning(f"Modelo {modelo} no disponible ({exc!r}); probando con {modelos[i + 1]}")

        # 6. Validar respuesta obtenida
        if not response.text:
            logger.warning("Gemini devolvió una respuesta vacía o bloqueada por filtros de seguridad.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La respuesta no pudo ser generada por los filtros de seguridad de la IA. Por favor formula tu duda con términos estrictamente matemáticos."
            )

        texto, verificacion = await verificar_respuesta(response.text)
        texto, grafica = await graficar_respuesta(texto)
        texto, narracion = narracion_respuesta(texto)
        return ChatResponse(respuesta=texto, verificacion=verificacion, grafica=grafica, narracion=narracion)

    except HTTPException:
        raise

    except Exception as exc:
        logger.error(f"Error durante la llamada a Gemini API: {exc}", exc_info=True)

        # Clasificación pedagógica de errores usando el código HTTP real de la API
        codigo = exc.code if isinstance(exc, genai_errors.APIError) else None
        # Google responde 400 con API_KEY_INVALID cuando la clave es incorrecta
        clave_invalida = codigo in (401, 403) or (codigo == 400 and "API_KEY_INVALID" in str(exc))

        if codigo == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Se ha excedido la cuota de peticiones a la API de Gemini. Por favor espera un minuto antes de enviar tu siguiente consulta."
            )
        elif clave_invalida:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La clave de API de Gemini provista es inválida o no tiene permisos. Verifica tu archivo .env."
            )
        elif codigo == 503:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El modelo de IA está saturado en este momento (alta demanda en Google). Espera unos segundos y vuelve a enviar tu pregunta."
            )
        elif codigo == 504 or isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="El cálculo tomó más tiempo de lo esperado (tiempo de espera agotado). Intenta reformular tu consulta de forma más puntual."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ocurrió un error al procesar tu consulta de cálculo con el tutor de IA. Por favor intenta nuevamente en unos instantes."
            )


# ============================================================================
# SERVIDO DE ARCHIVOS ESTÁTICOS Y FRONTEND
# ============================================================================

# Servir index.html en la raíz /
@app.get("/", include_in_schema=False)
async def servir_index():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="No se encontró el archivo estático index.html.")
    return FileResponse(index_path)


# Montar la carpeta static para CSS, JS y otros assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Si se ejecuta directamente `python app.py`, validar API key antes de arrancar
    if not GEMINI_API_KEY:
        print("\n" + "=" * 75)
        print("❌ AVISO: GEMINI_API_KEY no encontrada en las variables de entorno.")
        print("El servidor iniciará, pero las consultas requerirán que configures el archivo .env")
        print("Copia .env.example -> .env y añade tu clave obtenida en https://aistudio.google.com/")
        print("=" * 75 + "\n")

    print(f"🚀 Levantando Servidor Tutor de Cálculo en http://localhost:{PORT}")
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=True)
