import base64
import colorsys
import hashlib
import io
import os
import re
from html import escape

import streamlit as st
from PIL import Image, ImageOps, ImageStat

try:
    import openai
    from openai import OpenAI
except ImportError:  # sin la librería solo funciona el modo sin clave
    openai = None
    OpenAI = None

st.set_page_config(
    page_title="Visión · Daniel Flórez",
    page_icon="🏞️",
    layout="centered",
    initial_sidebar_state="expanded",
)

# =====================================================================
#  CONFIGURACIÓN
# =====================================================================
SIN_CLAVE = "Sin clave · análisis básico de la imagen"

# Todos estos servicios hablan el mismo "idioma" que OpenAI, así que usamos una sola librería.
# Los nombres de modelo cambian con frecuencia: si uno falla, usa «Cargar modelos».
PROVEEDORES = {
    SIN_CLAVE: {},
    "Google Gemini · plan gratuito": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "modelo": "gemini-flash-latest",
        "secreto": "GEMINI_API_KEY",
        "clave_url": "https://aistudio.google.com/apikey",
        "nota": "Gratis sin tarjeta, con límites por minuto y por día. En el plan gratuito, Google "
        "puede usar lo que envíes para mejorar sus productos: no subas fotos privadas.",
        "pasos": [
            "Entra a aistudio.google.com/apikey con tu cuenta de Google.",
            "Acepta los términos si te los pide.",
            "Pulsa «Create API key» y elige un proyecto (o crea uno nuevo).",
            "Copia la clave (empieza por «AIza») y pégala aquí. No la compartas ni la subas a GitHub.",
        ],
    },
    "Groq · plan gratuito": {
        "base_url": "https://api.groq.com/openai/v1",
        "modelo": "qwen/qwen3.6-27b",
        "secreto": "GROQ_API_KEY",
        "clave_url": "https://console.groq.com/keys",
        "nota": "Gratis sin tarjeta y muy rápido. Solo algunos modelos aceptan imágenes (los de "
        "«visión»): si falla, pulsa «Cargar modelos» y revisa la documentación de Groq.",
        "pasos": [
            "Entra a console.groq.com/keys e inicia sesión (Google, GitHub o correo).",
            "Pulsa «Create API Key» y ponle un nombre.",
            "Copia la clave y pégala aquí.",
        ],
    },
    "OpenRouter · modelos gratuitos": {
        "base_url": "https://openrouter.ai/api/v1",
        "modelo": "openrouter/free",
        "secreto": "OPENROUTER_API_KEY",
        "clave_url": "https://openrouter.ai/keys",
        "nota": "Los modelos «:free» no cobran, pero tienen tope diario de solicitudes y cambian "
        "con frecuencia. Elige uno que acepte imágenes.",
        "pasos": [
            "Entra a openrouter.ai/keys e inicia sesión.",
            "Pulsa «Create Key» y copia la clave.",
            "Pégala aquí y, si falla, pulsa «Cargar modelos» para ver los gratuitos.",
        ],
    },
    "OpenAI · de pago": {
        "base_url": None,
        "modelo": "gpt-4o-mini",
        "secreto": "OPENAI_API_KEY",
        "clave_url": "https://platform.openai.com/api-keys",
        "nota": "Requiere saldo en tu cuenta de OpenAI.",
        "pasos": [],
    },
    "Otro servicio compatible con OpenAI": {
        "base_url": "",
        "modelo": "",
        "secreto": "LLM_API_KEY",
        "clave_url": None,
        "nota": "Sirve para cualquier servicio con API compatible con OpenAI y modelos con visión "
        "(incluido Ollama en tu computador, que solo funciona si ejecutas la app en local).",
        "pasos": [],
    },
}

TAREAS = {
    "Describir la imagen": "Describe con detalle lo que ves en la imagen.",
    "Objetos y colores": "Haz una lista de los objetos y personas que ves y de los colores predominantes.",
    "Texto visible": (
        "Transcribe todo el texto que aparece en la imagen, respetando los saltos de línea. "
        "Si no hay texto, dilo."
    ),
    "Pregunta personalizada": "",
}

EXCLUIR_MODELOS = (
    "embed", "whisper", "tts", "imagen", "audio", "guard", "moderation",
    "veo", "lyria", "dall-e", "transcribe", "robotics", "computer-use",
)

LADO_MAXIMO = 1568  # las imágenes grandes se reducen antes de enviarlas

# Fondo de página tipo cuaderno: (imagen del patrón, tamaño del patrón)
PATRONES = {
    "Puntos": (
        "radial-gradient(circle, rgba(63,113,166,.30) 1.5px, transparent 1.7px)",
        "26px 26px",
    ),
    "Rayas": (
        "linear-gradient(rgba(63,113,166,.20) 1px, transparent 1px)",
        "100% 34px",
    ),
    "Cuadrícula": (
        "linear-gradient(rgba(63,113,166,.16) 1px, transparent 1px), "
        "linear-gradient(90deg, rgba(63,113,166,.16) 1px, transparent 1px)",
        "28px 28px, 28px 28px",
    ),
    "Liso": (None, None),
}

# =====================================================================
#  ESTILO (paleta fría basada en #3f71a6)
# =====================================================================
PRIMARIO = "#3f71a6"
OSCURO = "#1b2f45"
CLARO = "#eaf2f9"
SUAVE = "#a9c7e3"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Caveat:wght@500;600&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600&family=Playfair+Display:wght@500;600;700&display=swap');

html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; font-size: 1.06rem; }
.stApp { background-color: #f6fafd; __PATRON__ }
header[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 860px; padding-top: 3rem; padding-bottom: 4rem; }

/* Hero */
.hero { text-align: center; padding: 1rem 0 .5rem 0; }
.hero .etiqueta {
    font-family: 'Caveat', cursive; font-size: 1.8rem; font-weight: 600;
    color: __PRIMARIO__; line-height: 1;
}
.hero h1 {
    font-family: 'Playfair Display', serif; font-size: 3.1rem; color: __OSCURO__;
    margin: .3rem 0 .6rem 0; line-height: 1.12;
}
.hero h1 .marca {
    background: linear-gradient(transparent 62%, rgba(169, 199, 227, .75) 62%);
    padding: 0 .12em;
}
.hero p { color: #4d6479; font-size: 1.2rem; max-width: 620px; margin: 0 auto; }
.linea { width: 70px; height: 4px; border-radius: 4px; background: __PRIMARIO__; margin: 1.4rem auto; }
h2, h3 { font-family: 'Playfair Display', serif !important; color: __OSCURO__ !important; }

/* Tarjetas con "cinta washi" (contenedores con key="tarjeta_...") */
[class*="st-key-tarjeta"] {
    position: relative; box-sizing: border-box;
    background: #ffffff !important;
    border: 1px solid __SUAVE__99 !important;
    border-radius: 18px !important;
    box-shadow: 0 8px 24px rgba(63, 113, 166, .10);
    padding: 1.4rem 1.5rem 1.3rem 1.5rem !important;
}
[class*="st-key-tarjeta"]::before {
    content: ""; position: absolute; top: -10px; left: 28px; width: 80px; height: 20px;
    background: rgba(169, 199, 227, .75); border-radius: 2px;
    transform: rotate(-1.5deg); box-shadow: 0 1px 2px rgba(27, 47, 69, .10); z-index: 2;
}
[data-testid="stHeaderActionElements"] { display: none !important; }

/* Texto legible dentro de las tarjetas, también si el navegador está en modo oscuro */
[class*="st-key-tarjeta"] p,
[class*="st-key-tarjeta"] label,
[class*="st-key-tarjeta"] li,
[class*="st-key-tarjeta"] [data-testid="stWidgetLabel"] * { color: __OSCURO__ !important; }
[class*="st-key-tarjeta"] [data-testid="stCaptionContainer"] * { color: #4d6479 !important; }

/* Imagen */
[data-testid="stImage"] img { border-radius: 14px; box-shadow: 0 8px 22px rgba(27, 47, 69, .15); }

/* Datos de la imagen */
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: .8rem 0 .2rem 0; }
.chip {
    background: #f6fafd; border: 1px dashed __SUAVE__; border-radius: 999px;
    padding: 5px 14px; font-size: .88rem; font-weight: 500; color: __OSCURO__;
}
.paleta { display: flex; flex-wrap: wrap; gap: 12px; margin: .8rem 0; }
.muestra { width: 104px; text-align: center; font-size: .82rem; color: __OSCURO__; }
.muestra .color { height: 58px; border-radius: 12px; border: 1px solid rgba(27, 47, 69, .15); margin-bottom: 6px; }
.muestra b { display: block; font-weight: 600; }
.muestra span { font-family: 'IBM Plex Mono', monospace; font-size: .76rem; color: #6b8399; }
.resumen { color: #324b63; line-height: 1.6; }

/* Botones e inputs */
.stButton > button, .stDownloadButton > button {
    background: __PRIMARIO__; color: white; border: 1.5px solid __PRIMARIO__;
    border-radius: 999px; padding: .65rem 1.4rem; font-weight: 600; transition: all .2s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: __OSCURO__; border-color: __OSCURO__; color: white; transform: translateY(-2px);
}
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
    border-radius: 12px; border: 1px solid __SUAVE__;
}
[data-testid="stFileUploaderDropzone"] { background: __CLARO__; border: 2px dashed __SUAVE__; border-radius: 16px; }
[data-testid="stAlert"] { border-radius: 14px; }

/* Sidebar */
[data-testid="stSidebar"] { background: __OSCURO__; }
[data-testid="stSidebar"] * { color: #e6f0f9 !important; }

#MainMenu, footer { visibility: hidden; }
</style>
"""


def construir_css(patron: str) -> str:
    imagen, tamano = PATRONES[patron]
    base = "linear-gradient(180deg, #f6fafd 0%, #eaf2f9 100%)"
    if imagen:
        fondo = f"background-image: {imagen}, {base}; background-size: {tamano}, 100% 100%;"
    else:
        fondo = f"background-image: {base};"
    css = CSS.replace("__PATRON__", fondo)
    for token, valor in {
        "__PRIMARIO__": PRIMARIO,
        "__OSCURO__": OSCURO,
        "__CLARO__": CLARO,
        "__SUAVE__": SUAVE,
    }.items():
        css = css.replace(token, valor)
    return css


# =====================================================================
#  LÓGICA: IMAGEN (sin claves ni servicios externos)
# =====================================================================
def a_rgb(img: Image.Image) -> Image.Image:
    """Convierte a RGB; si hay transparencia, la pone sobre fondo blanco."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        fondo = Image.new("RGB", rgba.size, (255, 255, 255))
        fondo.paste(rgba, mask=rgba.split()[-1])
        return fondo
    return img.convert("RGB")


@st.cache_data(show_spinner=False, max_entries=10)
def preparar_imagen(datos: bytes) -> tuple:
    """Reduce la imagen y la guarda como JPEG sin metadatos (se elimina la ubicación GPS, etc.).

    Devuelve (bytes JPEG, (ancho, alto) enviado).
    """
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos)))
    img = a_rgb(img)
    if max(img.size) > LADO_MAXIMO:
        img.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=85, optimize=True)  # sin exif= => sin metadatos
    return salida.getvalue(), img.size


def nombre_color(rgb: tuple) -> str:
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h *= 360
    if v < 0.15:
        return "negro"
    if s < 0.12:
        return "blanco" if v > 0.85 else "gris"
    if h < 15 or h >= 345:
        return "rojo" if v >= 0.45 else "granate"
    if h < 40:
        return "naranja" if v >= 0.6 else "marrón"
    if h < 70:
        return "amarillo" if v >= 0.6 else "oliva"
    if h < 165:
        return "verde"
    if h < 200:
        return "turquesa"
    if h < 255:
        return "azul"
    if h < 290:
        return "morado"
    return "rosa"


@st.cache_data(show_spinner=False, max_entries=10)
def analisis_basico(datos: bytes) -> dict:
    """Datos de la imagen que se pueden calcular sin IA: tamaño, luz, contraste y colores."""
    original = Image.open(io.BytesIO(datos))
    formato = original.format or "desconocido"
    img = ImageOps.exif_transpose(original)
    ancho, alto = img.size

    tiene_gps = False
    try:
        tiene_gps = bool(original.getexif().get_ifd(0x8825))
    except Exception:
        pass

    pequena = a_rgb(img)
    pequena.thumbnail((200, 200))
    gris = ImageStat.Stat(pequena.convert("L"))
    brillo, contraste = gris.mean[0] / 255, gris.stddev[0] / 255

    cuantizada = pequena.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    paleta = cuantizada.getpalette()[:15]
    cuentas = sorted(cuantizada.getcolors(), reverse=True)
    total = sum(c for c, _ in cuentas)
    colores = []
    for cantidad, indice in cuentas:
        rgb = tuple(paleta[indice * 3 : indice * 3 + 3])
        colores.append({"rgb": rgb, "hex": "#%02x%02x%02x" % rgb, "nombre": nombre_color(rgb), "pct": cantidad / total})

    return {
        "formato": formato, "ancho": ancho, "alto": alto, "megapixeles": ancho * alto / 1e6,
        "orientacion": "horizontal" if ancho > alto * 1.05 else ("vertical" if alto > ancho * 1.05 else "cuadrada"),
        "brillo": brillo, "contraste": contraste, "colores": colores, "tiene_gps": tiene_gps,
    }


def resumen_basico(a: dict) -> str:
    luz = "oscura" if a["brillo"] < 0.3 else ("muy luminosa" if a["brillo"] > 0.7 else "con luz equilibrada")
    cont = "de alto contraste" if a["contraste"] > 0.25 else ("de bajo contraste" if a["contraste"] < 0.12 else "de contraste medio")
    colores = ", ".join(f"{c['nombre']} ({c['pct']:.0%})" for c in a["colores"][:3])
    return (
        f"Es una imagen {a['orientacion']} de {a['ancho']}×{a['alto']} píxeles "
        f"({a['megapixeles']:.1f} MP), {luz} y {cont}. Los colores que más aparecen son: {colores}."
    )


def html_basico(a: dict) -> str:
    chips = (
        f'<span class="chip">📐 {a["ancho"]}×{a["alto"]} px</span>'
        f'<span class="chip">🖼️ {escape(a["formato"])}</span>'
        f'<span class="chip">↔️ {a["orientacion"]}</span>'
        f'<span class="chip">💡 luz {a["brillo"]:.0%}</span>'
        f'<span class="chip">◐ contraste {a["contraste"]:.0%}</span>'
    )
    muestras = "".join(
        f'<div class="muestra"><div class="color" style="background:{c["hex"]}"></div>'
        f'<b>{c["nombre"]} · {c["pct"]:.0%}</b><span>{c["hex"]}</span></div>'
        for c in a["colores"]
    )
    return f'<div class="resumen">{escape(resumen_basico(a))}</div><div class="chips">{chips}</div><div class="paleta">{muestras}</div>'


# =====================================================================
#  LÓGICA: MODELOS CON VISIÓN (opcional, con clave)
# =====================================================================
def crear_cliente(config: dict, timeout: int = 90):
    return OpenAI(
        api_key=config["clave"],
        base_url=config["base_url"] or None,
        timeout=timeout,
        max_retries=1,
    )


def listar_modelos(config: dict) -> list:
    cliente = crear_cliente(config, timeout=30)
    ids = []
    for modelo in cliente.models.list():
        nombre = modelo.id.removeprefix("models/")
        if any(x in nombre.lower() for x in EXCLUIR_MODELOS):
            continue
        ids.append(nombre)
    if config["etiqueta"].startswith("OpenRouter"):
        ids = [i for i in ids if i.endswith(":free") or i == "openrouter/free"]
    return sorted(set(ids))


def limpiar_pensamiento(texto: str) -> str:
    """Algunos modelos incluyen su razonamiento entre <think>...</think>: no se muestra."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S)
    if "<think>" in texto:  # bloque todavía abierto durante la transmisión
        texto = texto.split("<think>")[0]
    return texto.strip()


def construir_mensajes(prompt: str, jpeg: bytes) -> list:
    imagen_b64 = base64.b64encode(jpeg).decode("utf-8")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagen_b64}"}},
            ],
        }
    ]


def analizar_con_ia(config: dict, prompt: str, jpeg: bytes, caja) -> str:
    """Envía la imagen al modelo y va mostrando la respuesta a medida que llega."""
    cliente = crear_cliente(config)
    mensajes = construir_mensajes(prompt, jpeg)
    texto = ""
    try:
        flujo = cliente.chat.completions.create(model=config["modelo"], messages=mensajes, stream=True)
        for trozo in flujo:
            if not trozo.choices:
                continue
            delta = trozo.choices[0].delta.content
            if delta:
                texto += delta
                caja.markdown(limpiar_pensamiento(texto) + " ▌")
    except Exception as error:
        if "stream" in str(error).lower() and not texto:  # el servicio no admite transmisión
            respuesta = cliente.chat.completions.create(model=config["modelo"], messages=mensajes)
            texto = respuesta.choices[0].message.content or ""
        else:
            raise
    final = limpiar_pensamiento(texto)
    if not final:
        raise ValueError("El modelo devolvió una respuesta vacía.")
    caja.markdown(final)
    return final


def explicar_error(error: Exception) -> str:
    if openai is not None:
        if isinstance(error, openai.AuthenticationError):
            return "La clave no es válida o no tiene permiso para este servicio."
        if isinstance(error, openai.RateLimitError):
            return (
                "Se alcanzó el límite del plan gratuito o el modelo está saturado. "
                "Espera un minuto, prueba otro modelo o usa el modo sin clave."
            )
        if isinstance(error, openai.NotFoundError):
            return "Ese modelo no existe en este servicio. Pulsa «Cargar modelos» y elige uno de la lista."
        if isinstance(error, openai.BadRequestError):
            return (
                "El servicio rechazó la solicitud. Lo más probable es que ese modelo no acepte "
                "imágenes: elige uno con visión."
            )
        if isinstance(error, openai.APIConnectionError):
            return "No se pudo conectar con el servicio. Revisa tu conexión a internet."
    return f"El servicio devolvió un error: {str(error)[:180]}"


def clave_guardada(nombre: str):
    """Busca la clave en los secretos de la app o en variables de entorno (nunca la escribe)."""
    try:
        valor = st.secrets.get(nombre)
        if valor:
            return str(valor)
    except Exception:
        pass
    return os.environ.get(nombre) or None


def mostrar_resultado(res: dict, caja=None):
    if res["modo"] == "local":
        st.markdown(html_basico(res["analisis"]), unsafe_allow_html=True)
        if res["analisis"]["tiene_gps"]:
            st.caption(
                "📍 Esta foto trae la ubicación GPS en sus metadatos. Al enviarla a un servicio "
                "de IA, esta app la elimina antes."
            )
        st.caption(
            "Sin IA solo se pueden medir datos de la imagen. Para saber qué objetos o escenas "
            "aparecen, elige un motor con clave (por ejemplo Gemini)."
        )
    else:
        (caja or st).markdown(res["texto"])
        st.caption(f"Respuesta de {res['modelo']}.")


# =====================================================================
#  PÁGINA
# =====================================================================
with st.sidebar:
    st.subheader("Cómo usarlo")
    st.markdown(
        "1. Sube una imagen o toma una foto.\n"
        "2. Elige cómo analizarla.\n"
        "3. Pulsa **Analizar la imagen**."
    )
    st.subheader("Privacidad")
    st.markdown(
        "Con un motor de IA, la imagen (reducida y sin metadatos) se envía a ese servicio. "
        "Sin clave, todo se queda en esta app."
    )
    st.subheader("Estilo de la página")
    patron = st.radio(
        "Fondo de cuaderno", list(PATRONES), horizontal=True, label_visibility="collapsed"
    )

st.markdown(construir_css(patron), unsafe_allow_html=True)

st.markdown(
    """
    <div class="hero">
        <div class="etiqueta">cuaderno de visión ✎</div>
        <h1>Análisis de <span class="marca">imagen</span></h1>
        <p>Sube una foto y descubre qué contiene, con o sin inteligencia artificial.</p>
        <div class="linea"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---- 1. Imagen ----
datos = None
with st.container(key="tarjeta_imagen"):
    st.subheader("1 · Tu imagen")
    origen = st.radio(
        "Origen", ["🖼️ Subir imagen", "📷 Cámara"], horizontal=True, label_visibility="collapsed"
    )
    if origen.startswith("🖼️"):
        archivo = st.file_uploader(
            "Sube una imagen", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed"
        )
    else:
        archivo = st.camera_input("Toma una foto", label_visibility="collapsed")

    if archivo is not None:
        datos = archivo.getvalue()
        try:
            Image.open(io.BytesIO(datos)).verify()
        except Exception:
            st.error("No se pudo abrir el archivo como imagen. Prueba con otro.")
            datos = None
    if datos is not None:
        st.image(datos, use_container_width=True)

huella = hashlib.md5(datos).hexdigest() if datos else None
if st.session_state.get("huella_imagen") != huella:
    st.session_state["huella_imagen"] = huella
    st.session_state.pop("resultado", None)

st.write("")

# ---- 2. Motor ----
with st.container(key="tarjeta_motor"):
    st.subheader("2 · Cómo analizarla")
    etiqueta = st.selectbox("Motor de análisis", list(PROVEEDORES), label_visibility="collapsed")
    preset = PROVEEDORES[etiqueta]
    config = {"modo": "local"}

    if etiqueta == SIN_CLAVE:
        st.caption(
            "Sin IA: la app mide el tamaño, la luz, el contraste y los colores dominantes de la "
            "imagen. Es gratis y no envía tu foto a ningún servicio."
        )
    else:
        st.caption(preset["nota"])
        if OpenAI is None:
            st.warning("Falta la librería `openai` en `requirements.txt` para usar este motor.")
        else:
            guardada = clave_guardada(preset["secreto"])
            if guardada:
                clave = guardada
                st.success("Se usa la clave guardada en la configuración de la app.")
            else:
                clave = st.text_input(
                    "Tu clave de API",
                    type="password",
                    key=f"clave_{etiqueta}",
                    placeholder="Pega tu clave aquí",
                )
                if preset["pasos"]:
                    with st.expander("¿Cómo consigo una clave gratis?"):
                        st.markdown("\n".join(f"{i}. {p}" for i, p in enumerate(preset["pasos"], 1)))

            base_url = preset["base_url"]
            if base_url == "":
                base_url = st.text_input("Dirección del servicio (base URL)", placeholder="https://.../v1")

            modelo_defecto = preset["modelo"]
            lista_clave = f"modelos_{etiqueta}"
            if st.session_state.get(lista_clave):
                lista = st.session_state[lista_clave]
                indice = lista.index(modelo_defecto) if modelo_defecto in lista else 0
                modelo = st.selectbox("Modelo (debe aceptar imágenes)", lista, index=indice)
            else:
                modelo = st.text_input(
                    "Modelo (debe aceptar imágenes)", value=modelo_defecto, key=f"modelo_{etiqueta}"
                )

            config_prueba = {"etiqueta": etiqueta, "base_url": base_url, "clave": clave, "modelo": modelo}
            if clave and st.button("Cargar modelos disponibles"):
                try:
                    with st.spinner("Consultando el servicio..."):
                        st.session_state[lista_clave] = listar_modelos(config_prueba)
                    if not st.session_state[lista_clave]:
                        st.info("El servicio no devolvió modelos de chat.")
                    st.rerun()
                except Exception as error:
                    st.error(explicar_error(error))

            if clave and modelo:
                config = {"modo": "llm", **config_prueba}
            elif not clave:
                st.info("Sin clave se usará el análisis básico de la imagen.")

st.write("")

# ---- 3. Pregunta ----
with st.container(key="tarjeta_pregunta"):
    st.subheader("3 · Qué quieres saber")
    if config["modo"] == "llm":
        tarea = st.radio("Tarea", list(TAREAS), horizontal=True, label_visibility="collapsed")
        detalle = st.text_area(
            "Contexto o pregunta (opcional)",
            placeholder="Ej: ¿Qué estilo de arquitectura tiene este edificio?",
            height=90,
        )
    else:
        tarea, detalle = None, ""
        st.caption("El análisis básico no necesita instrucciones. Elige un motor con clave para hacer preguntas.")
    analizar = st.button("Analizar la imagen", type="primary", use_container_width=True)

st.write("")

# ---- 4. Resultado ----
zona = st.empty()

if analizar:
    if datos is None:
        st.warning("Primero sube una imagen o toma una foto.")
    elif config["modo"] == "llm" and tarea == "Pregunta personalizada" and not detalle.strip():
        st.warning("Escribe tu pregunta en el cuadro de contexto.")
    else:
        with zona.container(key="tarjeta_resultado"):
            st.subheader("4 · Resultado")
            caja = st.empty()
            try:
                if config["modo"] == "llm":
                    prompt = TAREAS[tarea]
                    if detalle.strip():
                        prompt += f"\n\nContexto o pregunta del usuario: {detalle.strip()}"
                    prompt += "\n\nResponde en español."
                    with st.spinner("Analizando..."):
                        jpeg, _ = preparar_imagen(datos)
                        texto = analizar_con_ia(config, prompt.strip(), jpeg, caja)
                    st.session_state["resultado"] = {"modo": "llm", "texto": texto, "modelo": config["modelo"]}
                    st.caption(f"Respuesta de {config['modelo']}.")
                else:
                    with caja.container():
                        resultado = {"modo": "local", "analisis": analisis_basico(datos)}
                        mostrar_resultado(resultado)
                    st.session_state["resultado"] = resultado
            except Exception as error:
                caja.empty()
                st.error(explicar_error(error))
elif st.session_state.get("resultado"):
    with zona.container(key="tarjeta_resultado"):
        st.subheader("4 · Resultado")
        mostrar_resultado(st.session_state["resultado"])

st.write("")
st.caption("Análisis con el servicio de IA que elijas (opcional).")
