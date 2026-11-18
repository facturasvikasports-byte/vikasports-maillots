"""Programa de pedidos de maillots de gimnasia rítmica.

Para abrirlo: doble clic en "Abrir programa.bat", o en una terminal:
    .venv\\Scripts\\streamlit run app.py
"""

import base64
import hmac
import html
import io
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps
from sqlalchemy import create_engine, inspect, text

CARPETA = Path(__file__).parent
ARCHIVO_PRECIOS = CARPETA / "precios.json"
BASE_DATOS = CARPETA / "pedidos.db"
IMAGENES = CARPETA / "imagenes"

try:
    HORA_ESPANA = ZoneInfo("Europe/Madrid")
except Exception:
    HORA_ESPANA = None  # Windows sin datos de zonas horarias: se usa la hora del ordenador


def ahora():
    """Fecha y hora de España, también en el servidor de internet (que va en hora UTC)."""
    return datetime.now(HORA_ESPANA)


ESTADOS = ["Nuevo", "Presupuesto enviado", "Confirmado", "En confección", "Entregado", "Cancelado"]
# Medidas que se piden cuando el maillot es a medida, por bloques.
MEDIDAS = {
    "Cuerpo": ["Pecho", "Cintura", "Cadera", "Tiro espalda", "Tiro total", "Braga"],
    "Manga": ["Manga larga", "Bíceps", "Muñeca"],
    "Mono": ["Tiro exterior", "Muslo", "Gemelo", "Tobillo"],
}
TODAS_LAS_MEDIDAS = [m for lista in MEDIDAS.values() for m in lista]

# Con la técnica de recorte el precio se consulta y estos grupos no se muestran.
OCULTOS_EN_RECORTE = ["Diseño", "Forro", "Tejido", "Tallaje"]
LADOS_MANGA = ["Brazo derecho", "Brazo izquierdo"]

# Campos de la base de datos, en el orden en que se muestran y exportan.
COLUMNAS = [
    "id", "fecha", "estado", "nombre", "ciudad", "club", "telefono", "email",
    "producto", "cantidad", "gimnasta", "modelo", "tecnica", "diseno", "forro", "tejido", "falda", "mangas", "tallaje",
    "talla", "medidas", "extras", "imagenes", "complementos", "descripcion", "precio_unidad", "total",
]

ESTILO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');

/* Colores del logo de Vika Sports */
:root {
  --magenta: #C0157E;
  --magenta-oscuro: #8E0E5C;
  --turquesa: #00B5BE;
  --turquesa-claro: #E3F6F7;
  --tinta: #3C3C3C;
  --gris: #6F7A7C;
  --linea: #DCECEE;
}
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li, .stApp h1, .stApp h2, .stApp h3 {
  font-family: "Montserrat", "Segoe UI", system-ui, sans-serif;
}
.stApp h1, .stApp h2, .stApp h3 { font-weight: 800; letter-spacing: -0.01em; color: var(--tinta); }

/* Barra superior con el logo, siempre visible */
header[data-testid="stHeader"] { background: transparent; }
/* Sin la barra de Streamlit (Fork, GitHub, menú): así no tapa el botón de WhatsApp */
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"], header[data-testid="stHeader"] * { pointer-events: none !important; }
header[data-testid="stHeader"] button, header[data-testid="stHeader"] button *,
header[data-testid="stHeader"] a { pointer-events: auto !important; }
.barra-marca {
  position: fixed; top: 0; left: 0; right: 0; height: 64px; z-index: 999980;
  background: rgba(255, 255, 255, .96); backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--linea); box-shadow: 0 2px 14px rgba(0, 120, 128, .06);
  display: flex; align-items: center; justify-content: center;
  padding-top: env(safe-area-inset-top, 0px);
}
.barra-marca img { height: 44px; width: auto; max-width: 70vw; object-fit: contain; }
.whatsapp {
  position: absolute; right: 24px; top: 50%; transform: translateY(-50%);
  display: flex; align-items: center; gap: .55rem; text-decoration: none !important;
  background: #25D366; color: #fff !important; border-radius: 999px;
  padding: .45rem 1rem .45rem .5rem; box-shadow: 0 4px 12px rgba(37, 211, 102, .30);
  transition: transform .15s ease, box-shadow .15s ease;
}
.whatsapp:hover { transform: translateY(-50%) scale(1.04); box-shadow: 0 6px 16px rgba(37, 211, 102, .40); }
.whatsapp:focus-visible { outline: 3px solid var(--turquesa); outline-offset: 2px; }
.whatsapp .icono {
  width: 32px; height: 32px; border-radius: 50%; background: #fff;
  display: grid; place-items: center; flex: none;
}
.whatsapp .icono svg { width: 20px; height: 20px; fill: #25D366; }
.whatsapp .texto { display: flex; flex-direction: column; line-height: 1.1; }
.whatsapp .texto small { font-size: .66rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; opacity: .9; }
.whatsapp .texto b { font-size: .98rem; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: .02em; }
.block-container { padding-top: 6rem; max-width: 1150px; }
section[data-testid="stSidebar"] { padding-top: 64px; }

/* Cabecera */
.cabecera {
  position: relative; overflow: hidden;
  background: var(--magenta); color: #fff;
  border-radius: 22px; padding: 2.2rem 2rem 2rem; margin-bottom: 1.6rem;
}
.cabecera svg { position: absolute; right: -40px; top: -10px; width: 520px; max-width: 80%; }
.cabecera .etiqueta {
  display: inline-block; font-size: .76rem; font-weight: 700; letter-spacing: .16em;
  text-transform: uppercase; color: #BFF3F5; margin-bottom: .5rem; position: relative;
}
.cabecera h1 {
  color: #fff !important; font-size: clamp(2rem, 5vw, 3rem) !important; font-weight: 800 !important;
  line-height: 1.05 !important; margin: 0 0 .6rem !important; padding: 0 !important; max-width: 14ch; position: relative;
}
.cabecera p { color: #FBE3F1; font-size: 1.05rem; margin: 0; max-width: 42ch; position: relative; }

/* Tarjetas de cada paso */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.paso) {
  background: #fff; border: 1px solid var(--linea) !important; border-radius: 20px;
  box-shadow: 0 6px 24px rgba(0, 120, 128, .06); padding: .6rem .5rem;
}
.paso { display: flex; gap: .9rem; align-items: center; margin-bottom: .2rem; }
.paso .num {
  flex: none; width: 2.3rem; height: 2.3rem; border-radius: 50%;
  background: var(--turquesa); color: #fff; font-weight: 800; font-size: 1.05rem;
  display: grid; place-items: center;
}
.paso h3 { margin: 0 !important; padding: 0 !important; font-size: 1.3rem !important; }
.paso p { margin: 0; color: var(--gris); font-size: .9rem; }

/* Etiquetas de los campos */
.stApp label p { font-weight: 600; font-size: .93rem; color: var(--tinta); }

/* Botones de opción grandes */
div[data-testid="stButtonGroup"] button {
  min-height: 2.8rem; padding: .5rem 1.05rem; font-size: 1rem; border-radius: 999px;
}
div[data-testid="stButtonGroup"] button:hover { border-color: var(--turquesa) !important; }
button[data-variant="pills"][aria-checked="true"],
button[data-variant="pills"][aria-pressed="true"] {
  background: var(--magenta) !important; border-color: var(--magenta) !important;
  box-shadow: 0 4px 12px rgba(192, 21, 126, .28);
}
button[data-variant="pills"][aria-checked="true"] p,
button[data-variant="pills"][aria-pressed="true"] p { color: #fff !important; font-weight: 600; }

/* Campos de texto */
.stApp input, .stApp textarea { font-size: 1rem !important; }

/* Presupuesto fijo a la vista */
div[data-testid="stColumn"]:has(.ancla-resumen) { position: sticky; top: 80px; align-self: flex-start; }
.resumen {
  background: #fff; border: 1px solid var(--linea); border-radius: 20px;
  box-shadow: 0 10px 30px rgba(0, 120, 128, .10); overflow: hidden;
}
.resumen .arriba { background: var(--turquesa-claro); padding: 1.1rem 1.3rem; border-bottom: 3px solid var(--turquesa); }
.resumen .arriba .eti { font-size: .74rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: var(--magenta); }
.resumen .arriba h3 { margin: .15rem 0 0 !important; padding: 0 !important; font-size: 1.35rem !important; }
.resumen ul { list-style: none; margin: 0; padding: 1rem 1.3rem .4rem; }
.resumen li { display: flex; justify-content: space-between; gap: 1rem; padding: .35rem 0; border-bottom: 1px dashed var(--linea); font-size: .92rem; }
.resumen li span:last-child { font-variant-numeric: tabular-nums; white-space: nowrap; font-weight: 600; }
.resumen .vacio { padding: 1rem 1.3rem; color: var(--gris); font-size: .92rem; }
.resumen .cuentas { padding: .4rem 1.3rem 0; color: var(--gris); font-size: .9rem; display: flex; justify-content: space-between; }
.resumen .total { padding: .4rem 1.3rem 1.2rem; display: flex; justify-content: space-between; align-items: baseline; }
.resumen .total b { font-size: 1rem; }
.resumen .total strong {
  font-size: 2.2rem; font-weight: 800; color: var(--magenta);
  font-variant-numeric: tabular-nums; line-height: 1;
}
.nota { color: var(--gris); font-size: .8rem; margin-top: .3rem; }

/* Botón de enviar */
button[data-testid="stBaseButton-primary"] {
  min-height: 3.3rem; border-radius: 14px; box-shadow: 0 8px 20px rgba(192, 21, 126, .30);
}
button[data-testid="stBaseButton-primary"] p { font-size: 1.1rem; font-weight: 700; }

/* Ficha de cada pedido (página Base de datos) */
.ficha-cab {
  display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;
  background: var(--magenta); color: #fff; border-radius: 20px; padding: 1.2rem 1.5rem; margin: .6rem 0 1rem;
}
.ficha-cab .eti { font-size: .74rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: #BFF3F5; }
.ficha-cab h2 { color: #fff !important; margin: .1rem 0 .1rem !important; padding: 0 !important; font-size: 1.8rem !important; }
.ficha-cab .sub { color: #FBE3F1; font-size: .95rem; }
.ficha-cab .importe { text-align: right; }
.ficha-cab .importe strong { display: block; font-size: 1.9rem; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: .3rem; }
.chip-estado {
  display: inline-block; padding: .25rem .8rem; border-radius: 999px; background: #fff;
  font-size: .8rem; font-weight: 700;
}

@media (max-width: 640px) {
  .ficha-cab .importe { text-align: left; }
  .barra-marca { height: 56px; justify-content: flex-start; padding-left: 52px; }
  .barra-marca img { height: 30px; max-width: 42vw; }
  .whatsapp { right: 10px; padding: .3rem .7rem .3rem .3rem; gap: .4rem; }
  .whatsapp .icono { width: 26px; height: 26px; }
  .whatsapp .icono svg { width: 16px; height: 16px; }
  .whatsapp .texto small { display: none; }
  .whatsapp .texto b { font-size: .85rem; }
  .cabecera svg { opacity: .35; top: -50px; }
  .block-container { padding-top: 5rem; }
}
</style>
"""

# Cintas de gimnasia en turquesa y blanco, como en el logo.
CINTA = """
<svg viewBox="0 0 520 220" fill="none" aria-hidden="true">
  <path d="M10 170 C 90 40, 160 210, 250 110 S 400 10, 510 90" stroke="#3FD3DA" stroke-width="12" stroke-linecap="round" opacity=".85"/>
  <path d="M40 200 C 130 90, 200 230, 300 140 S 440 60, 520 140" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round" opacity=".45"/>
</svg>
"""


# ---------------------------------------------------------------- datos

def secreto(nombre):
    """Lee un valor de los secretos de Streamlit Cloud. En tu ordenador no hay secretos y devuelve ""."""
    try:
        return str(st.secrets.get(nombre, ""))
    except Exception:
        return ""


def motor():
    """Conexión a la base de datos: Supabase en internet, o el archivo pedidos.db en tu ordenador."""
    # Se pasan las columnas para que, si el programa trae columnas nuevas,
    # se vuelva a preparar la tabla aunque la conexión ya estuviera abierta.
    return motor_para(tuple(COLUMNAS))


@st.cache_resource
def motor_para(columnas):
    url = secreto("DATABASE_URL")
    if url:
        url = url.replace("postgres://", "postgresql+psycopg://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
    else:
        url = f"sqlite:///{BASE_DATOS.as_posix()}"
    eng = create_engine(url, pool_pre_ping=True)
    preparar_tablas(eng)
    return eng


def preparar_tablas(eng):
    postgres = eng.dialect.name == "postgresql"
    clave = "id SERIAL PRIMARY KEY" if postgres else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    decimal = "DOUBLE PRECISION" if postgres else "REAL"
    with eng.begin() as con:
        con.execute(text(f"""
            CREATE TABLE IF NOT EXISTS pedidos (
                {clave},
                fecha TEXT, estado TEXT,
                nombre TEXT, ciudad TEXT, club TEXT, telefono TEXT, email TEXT,
                producto TEXT, cantidad INTEGER,
                gimnasta TEXT, modelo TEXT, tecnica TEXT, diseno TEXT, forro TEXT, tejido TEXT, falda TEXT, mangas TEXT, tallaje TEXT,
                talla TEXT, medidas TEXT, extras TEXT, imagenes TEXT, complementos TEXT, descripcion TEXT,
                precio_unidad {decimal}, total {decimal}
            )"""))
        con.execute(text("CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)"))
        # Imágenes de diseño que adjunta el cliente, unidas a su pedido.
        con.execute(text(f"""
            CREATE TABLE IF NOT EXISTS imagenes (
                {clave}, pedido_id INTEGER, nombre TEXT, datos {"BYTEA" if postgres else "BLOB"}
            )"""))
        if postgres:
            # En Supabase: nadie más que el programa puede leer o cambiar estas tablas.
            con.execute(text("ALTER TABLE pedidos ENABLE ROW LEVEL SECURITY"))
            con.execute(text("ALTER TABLE configuracion ENABLE ROW LEVEL SECURITY"))
            con.execute(text("ALTER TABLE imagenes ENABLE ROW LEVEL SECURITY"))
    # Añadir las columnas nuevas a una base de datos creada con una versión anterior.
    existentes = {c["name"] for c in inspect(eng).get_columns("pedidos")}
    with eng.begin() as con:
        for columna in COLUMNAS:
            if columna not in existentes:
                con.execute(text(f"ALTER TABLE pedidos ADD COLUMN {columna} TEXT"))


@st.cache_data(ttl=300)
def cargar_config():
    """Precios y opciones. La primera vez, o cuando precios.json trae una versión nueva
    de las opciones, se copian de precios.json a la base de datos."""
    archivo = ARCHIVO_PRECIOS.read_text(encoding="utf-8")
    with motor().begin() as con:
        valor = con.execute(text("SELECT valor FROM configuracion WHERE clave = 'precios'")).scalar()
        if valor is None:
            valor = archivo
            con.execute(text("INSERT INTO configuracion (clave, valor) VALUES ('precios', :v)"), {"v": valor})
        elif json.loads(valor).get("version", 1) < json.loads(archivo).get("version", 1):
            valor = json.dumps(actualizar_config(json.loads(valor), json.loads(archivo)), ensure_ascii=False, indent=2)
            con.execute(text("UPDATE configuracion SET valor = :v WHERE clave = 'precios'"), {"v": valor})
    return json.loads(valor)


def actualizar_config(guardada, nueva):
    """Toma las opciones de la versión nueva, pero conserva los precios que ya se
    habían cambiado en la página Precios para las opciones que siguen existiendo."""
    if guardada.get("version", 1) >= 2:  # la versión 1 tenía otras opciones: se sustituye entera
        nueva["precio_base"] = guardada.get("precio_base", nueva["precio_base"])
        for grupo, opciones in nueva["opciones"].items():
            for opcion in opciones:
                if opcion in guardada["opciones"].get(grupo, {}):
                    opciones[opcion] = guardada["opciones"][grupo][opcion]
        for grupo, datos in nueva.get("extras", {}).items():
            antes = guardada.get("extras", {}).get(grupo, {}).get("opciones", {})
            for opcion in datos["opciones"]:
                if opcion in antes:
                    datos["opciones"][opcion] = antes[opcion]
    return nueva


def guardar_config(config):
    valor = json.dumps(config, ensure_ascii=False, indent=2)
    with motor().begin() as con:
        con.execute(text("UPDATE configuracion SET valor = :v WHERE clave = 'precios'"), {"v": valor})
    if not secreto("DATABASE_URL"):
        ARCHIVO_PRECIOS.write_text(valor, encoding="utf-8")  # copia local de los precios
    cargar_config.clear()


def guardar_pedido(pedido, imagenes=()):
    """Guarda el pedido y sus imágenes de diseño. Devuelve el número de pedido."""
    campos = [c for c in COLUMNAS if c != "id"]
    with motor().begin() as con:
        numero = con.execute(
            text(f"INSERT INTO pedidos ({', '.join(campos)}) VALUES ({', '.join(':' + c for c in campos)}) RETURNING id"),
            {c: pedido[c] for c in campos},
        ).scalar()
        for nombre, datos in imagenes:
            con.execute(text("INSERT INTO imagenes (pedido_id, nombre, datos) VALUES (:p, :n, :d)"),
                        {"p": numero, "n": nombre, "d": datos})
    return numero


def leer_imagenes(id_pedido):
    with motor().connect() as con:
        filas = con.execute(text("SELECT nombre, datos FROM imagenes WHERE pedido_id = :p ORDER BY id"),
                            {"p": id_pedido}).all()
    return [(nombre, bytes(datos)) for nombre, datos in filas]


def preparar_imagen(archivo):
    """Reduce la foto a 1600 px como máximo y la guarda en JPG, para no llenar la base de datos."""
    imagen = ImageOps.exif_transpose(Image.open(archivo))
    imagen.thumbnail((1600, 1600))
    if imagen.mode in ("RGBA", "LA", "P"):
        imagen = imagen.convert("RGBA")
        fondo = Image.new("RGB", imagen.size, "white")
        fondo.paste(imagen, mask=imagen.split()[-1])
        imagen = fondo
    salida = io.BytesIO()
    imagen.convert("RGB").save(salida, "JPEG", quality=85)
    return Path(archivo.name).stem + ".jpg", salida.getvalue()


def leer_pedidos():
    with motor().connect() as con:
        # Todas las columnas, también las de versiones antiguas, para no perder ningún dato.
        pedidos = pd.read_sql_query(text("SELECT * FROM pedidos ORDER BY id DESC"), con)
    for col in COLUMNAS:
        if col not in pedidos:
            pedidos[col] = None
    for col in ["cantidad", "precio_unidad", "total"]:
        pedidos[col] = pd.to_numeric(pedidos[col], errors="coerce").fillna(0)
    pedidos["fecha_dt"] = pd.to_datetime(pedidos["fecha"], format="%Y-%m-%d %H:%M", errors="coerce")
    return pedidos


def cambiar_estado(id_pedido, estado):
    with motor().begin() as con:
        con.execute(text("UPDATE pedidos SET estado = :e WHERE id = :i"), {"e": estado, "i": id_pedido})


def menu_gestion():
    """Enlaces entre las páginas de gestión (el menú lateral va oculto para los clientes)."""
    a, b, c = st.columns(3)
    a.page_link(PAGINA_BASE_DATOS, label="Base de datos", icon="📋")
    b.page_link(PAGINA_PRECIOS, label="Precios", icon="💶")
    c.page_link(PAGINA_PEDIDO, label="Formulario de pedido", icon="📝")


def acceso_gestion():
    """Pide la contraseña de gestión en internet. En tu ordenador no se pide."""
    clave = secreto("CLAVE_GESTION")
    if not clave or st.session_state.get("gestion_ok"):
        return True
    st.title("Acceso a gestión")
    st.caption("Esta parte es solo para Vika Sports.")
    with st.form("acceso"):
        intento = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if hmac.compare_digest(intento.encode(), clave.encode()):
                st.session_state.gestion_ok = True
                st.rerun()
            st.error("La contraseña no es correcta.")
    return False


# ---------------------------------------------------------------- cálculo

def euros(valor):
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto} €"


def calcular(config, elecciones, cantidad):
    """Devuelve las líneas del presupuesto, el precio por maillot y el total."""
    lineas = []
    unidad = config["precio_base"]
    if unidad:
        lineas.append(("Precio base", unidad))
    for grupo, eleccion in elecciones.items():
        # Un grupo de varias opciones (por ejemplo Tejido) devuelve una lista.
        for opcion in (eleccion if isinstance(eleccion, list) else [eleccion] if eleccion else []):
            precio = config["opciones"][grupo].get(opcion, 0)
            unidad += precio
            lineas.append((f"{grupo}: {opcion}", precio))
    return lineas, unidad, unidad * cantidad


def clave_extra(grupo, opcion=""):
    return f"ex_{grupo}_{opcion}"


def extras_elegidos(config):
    """Extras del pedido como (concepto, precio). Se suman una vez al total, no por maillot."""
    s = st.session_state
    lineas = []
    for grupo, datos in config.get("extras", {}).items():
        if datos.get("por_unidad"):
            for opcion, precio in datos["opciones"].items():
                n = int(s.get(clave_extra(grupo, opcion)) or 0)
                if n:
                    lineas.append((f"{grupo} {opcion.lower()} × {n}", precio * n))
        else:
            opcion = s.get(clave_extra(grupo))
            if opcion in datos["opciones"]:
                lineas.append((f"{grupo}: {opcion}", datos["opciones"][opcion]))
    return lineas


# ---------------------------------------------------------------- página: nuevo pedido

TEXTOS = ["nombre", "ciudad", "club", "telefono", "email", "gimnasta", "complementos", "descripcion"]
OBLIGATORIOS = {"nombre": "Nombre y apellido", "ciudad": "Ciudad", "telefono": "Teléfono", "gimnasta": "Gimnasta"}


# Columna de la base de datos donde se guarda cada grupo de opciones.
COLUMNA_DE_GRUPO = {
    "Técnica": "tecnica", "Diseño": "diseno", "Forro": "forro", "Tejido": "tejido",
    "Falda": "falda", "Mangas": "mangas", "Tallaje": "tallaje",
}


def clave_grupo(grupo):
    return "op_" + grupo


def clave_disenos():
    return f"disenos_{st.session_state.get('n_formulario', 0)}"


def es_varios(config, grupo):
    """Grupos opcionales en los que se puede elegir más de una opción."""
    return grupo in config.get("varios", [])


def es_recorte():
    return st.session_state.get(clave_grupo("Técnica")) == "Recorte"


def grupos_visibles(config):
    return [g for g in config["opciones"] if not (es_recorte() and g in OCULTOS_EN_RECORTE)]


def grupos_obligatorios(config):
    return [g for g in grupos_visibles(config) if not es_varios(config, g)]


def elecciones_actuales(config):
    """Opciones elegidas en los grupos que se ven. El recorte siempre es a medida."""
    elecciones = {g: st.session_state.get(clave_grupo(g)) for g in grupos_visibles(config)}
    if es_recorte():
        elecciones["Tallaje"] = "A medida"
    return elecciones


def una_manga():
    """Si se ha elegido una sola manga, hay que decir en qué brazo va."""
    return (st.session_state.get(clave_grupo("Mangas")) or "").startswith("1 manga")


def lleva_manga_larga():
    return "larga" in (st.session_state.get(clave_grupo("Mangas")) or "")


def medidas_visibles():
    bloques = ["Cuerpo"]
    if lleva_manga_larga():
        bloques.append("Manga")
    if st.session_state.get("es_mono"):
        bloques.append("Mono")
    return bloques


def requisitos(config):
    """Cada dato obligatorio con si ya está rellenado o no."""
    s = st.session_state
    lista = [(etiqueta, bool(s.get(clave, "").strip())) for clave, etiqueta in OBLIGATORIOS.items()]
    lista += [(g, bool(s.get(clave_grupo(g)))) for g in grupos_obligatorios(config)]
    if elecciones_actuales(config).get("Tallaje") == "Talla":
        lista.append(("Talla", bool(s.get("talla"))))
    if una_manga():
        lista.append(("Brazo de la manga", bool(s.get("manga_lado"))))
    return lista


def datos_que_faltan(config):
    return [etiqueta for etiqueta, hecho in requisitos(config) if not hecho]


def texto_pedido(numero, p):
    """Todos los datos del pedido en un mensaje de WhatsApp."""
    filas = [
        f"*NUEVO PEDIDO N.º {numero}* · {p['fecha']}",
        "",
        "*Cliente*",
        f"Nombre: {p['nombre']}",
        f"Teléfono: {p['telefono']}",
        f"Email: {p['email'] or '-'}",
        f"Ciudad: {p['ciudad']}",
        f"Club: {p['club'] or '-'}",
        "",
        "*Maillot*",
        f"Gimnasta: {p['gimnasta']}",
        *([f"*Modelo de catálogo: {p['modelo']}*"] if p.get("modelo") else []),
        f"Producto: {p['producto']}",
        f"Cantidad: {int(p['cantidad'] or 0)}",
        f"Técnica: {p['tecnica']}",
    ]
    for etiqueta, col in [("Diseño", "diseno"), ("Forro", "forro"), ("Tejido", "tejido"),
                          ("Falda", "falda"), ("Mangas", "mangas"), ("Tallaje", "tallaje"), ("Talla", "talla")]:
        if p[col]:
            filas.append(f"{etiqueta}: {p[col]}")
    if p["medidas"]:
        filas += ["", "*Medidas (cm)*"] + [b.strip() for b in p["medidas"].split(";")]
    if p.get("extras"):
        filas += ["", "*Extras*"] + [e.strip() for e in p["extras"].split(";")]
    if p.get("imagenes"):
        n = len(p["imagenes"].split(", "))
        filas += ["", f"*Diseño:* {n} imagen{'es' if n > 1 else ''} adjunta{'s' if n > 1 else ''} en el pedido"]
    filas += ["", f"Complementos: {p['complementos'] or '-'}", f"Descripción: {p['descripcion'] or '-'}", ""]
    if p["tecnica"] == "Recorte":
        filas.append("*Precio: consultar (recorte)*")
    else:
        filas.append(f"Precio por maillot: {euros(p['precio_unidad'])}")
        filas.append(f"*TOTAL: {euros(p['total'])}*")
    return "\n".join(filas)


def avisar_por_whatsapp(mensaje):
    """Manda el pedido al WhatsApp de Vika Sports con CallMeBot, si está configurado.
    Si falla, el pedido ya está guardado igualmente."""
    clave = secreto("CALLMEBOT_APIKEY")
    if not clave:
        return
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": "+34" + WHATSAPP_NUMERO.replace(" ", ""), "text": mensaje, "apikey": clave})
    try:
        urllib.request.urlopen(url, timeout=15).read()
    except Exception:
        pass


def enviar_pedido(config):
    s = st.session_state
    faltan = datos_que_faltan(config)
    if faltan:
        s.aviso = ("error", "Te falta rellenar: " + ", ".join(faltan) + ".")
        return

    imagenes = []
    for archivo in s.get(clave_disenos()) or []:
        try:
            imagenes.append(preparar_imagen(archivo))
        except Exception:
            s.aviso = ("error", f"No se pudo abrir la imagen «{archivo.name}». Prueba con una foto JPG o PNG.")
            return

    elecciones = elecciones_actuales(config)
    recorte = es_recorte()
    _, unidad, total = calcular(config, elecciones, s.cantidad)
    extras = extras_elegidos(config)
    total += sum(p for _, p in extras)
    texto_de = {g: ", ".join(v) if isinstance(v, list) else (v or "") for g, v in elecciones.items()}
    if una_manga():
        texto_de["Mangas"] += f" ({s.manga_lado.lower()})"
    medidas = ""
    if elecciones.get("Tallaje") == "A medida":
        bloques = medidas_visibles()
        medidas = "; ".join(
            f"{b}: " + ", ".join(f"{m} {s['m_' + m]:g} cm" if s.get("m_" + m) else f"{m} -" for m in MEDIDAS[b]) for b in bloques
        )

    pedido = {
        "fecha": ahora().strftime("%Y-%m-%d %H:%M"),
        "estado": "Nuevo",
        **{c: s.get(c, "").strip() for c in TEXTOS},
        "producto": s.get("producto") or "",
        "cantidad": s.cantidad,
        **{col: texto_de.get(grupo, "") for grupo, col in COLUMNA_DE_GRUPO.items()},
        "talla": (s.get("talla") or "") if elecciones.get("Tallaje") == "Talla" else "",
        "medidas": medidas,
        "extras": "; ".join(f"{c} ({euros(p)})" for c, p in extras),
        "imagenes": ", ".join(nombre for nombre, _ in imagenes),
        "modelo": texto_modelo(s.get("modelo")),
        # Con recorte el precio se consulta: se deja en blanco.
        "precio_unidad": None if recorte else unidad,
        "total": None if recorte else total,
    }
    numero = guardar_pedido(pedido, imagenes)
    s.ultimo_pedido = texto_pedido(numero, pedido)
    avisar_por_whatsapp(s.ultimo_pedido)
    if recorte:
        s.aviso = ("ok", f"¡Pedido n.º {numero} enviado! Te contactaremos con el precio para confirmarlo.")
    else:
        s.aviso = ("ok", f"¡Pedido n.º {numero} enviado! Total: {euros(total)}. Te contactaremos para confirmarlo.")

    # Vaciar el formulario para el siguiente pedido.
    for c in TEXTOS:
        s[c] = ""
    for g in config["opciones"]:
        s[clave_grupo(g)] = [] if es_varios(config, g) else None
    for m in TODAS_LAS_MEDIDAS:
        s["m_" + m] = None
    for grupo, datos in config.get("extras", {}).items():
        if datos.get("por_unidad"):
            for opcion in datos["opciones"]:
                s[clave_extra(grupo, opcion)] = 0
        else:
            s[clave_extra(grupo)] = None
    # El campo de imágenes no se puede vaciar: se cambia por uno nuevo.
    s.n_formulario = s.get("n_formulario", 0) + 1
    s.modelo = None
    s.talla = None
    s.manga_lado = None
    s.es_mono = False
    s.cantidad = 1


@st.cache_data
def imagen_en_linea(nombre):
    datos = base64.b64encode((IMAGENES / nombre).read_bytes()).decode()
    return f"data:image/png;base64,{datos}"


WHATSAPP_NUMERO = "662 448 237"
WHATSAPP_ENLACE = "https://wa.me/34662448237"

# Catálogo de maillots: el botón «Lo quiero» abre este formulario con ?modelo=VKS-221
CATALOGO_URL = "https://facturasvikasports-byte.github.io/catalogo/"
ARCHIVO_CATALOGO = CARPETA / "catalogo.json"


@st.cache_data
def cargar_catalogo():
    """{código: {nombre, seccion}} de los modelos del catálogo."""
    try:
        return json.loads(ARCHIVO_CATALOGO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def texto_modelo(codigo):
    if not codigo:
        return ""
    datos = cargar_catalogo().get(codigo, {})
    return f"{codigo} · {datos['nombre']}" if datos else codigo


def modelo_de_enlace():
    """Si se llega desde el catálogo (?modelo=VKS-221), deja elegido ese modelo y «De catálogo»."""
    s = st.session_state
    codigo = st.query_params.get("modelo")
    if codigo and codigo in cargar_catalogo() and s.get("modelo_del_enlace") != codigo:
        s.modelo_del_enlace = codigo
        s.modelo = codigo
        s[clave_grupo("Diseño")] = "De catálogo"


def quitar_modelo():
    st.session_state.modelo = None
    st.query_params.pop("modelo", None)


def bloque_modelo():
    """Tarjeta con el modelo elegido en el catálogo, o un enlace para ir a verlo."""
    codigo = st.session_state.get("modelo")
    if not codigo:
        st.markdown(f"¿Aún no tienes diseño? **[Mira nuestro catálogo de maillots →]({CATALOGO_URL})**")
        return
    datos = cargar_catalogo().get(codigo, {})
    with st.container(border=True):
        foto, texto = st.columns([1, 3], vertical_alignment="center")
        foto.image(f"{CATALOGO_URL}{codigo}-frente.webp", width=110)
        texto.markdown(f"**Modelo elegido del catálogo**  \n### {datos.get('nombre', codigo)}\n"
                       f"{codigo} · {datos.get('seccion', '')}")
        a, b = texto.columns(2)
        a.link_button("Cambiar modelo", f"{CATALOGO_URL}#{codigo}", width="stretch")
        b.button("Quitar", on_click=quitar_modelo, width="stretch")
ICONO_WHATSAPP = (
    "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148"
    "-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761"
    "-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025"
    "-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372"
    "-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694"
    ".625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57"
    "-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51"
    "-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437"
    " 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945"
    "L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48"
    "-8.413Z'/></svg>"
)


def mostrar_marca():
    """Estilos y barra superior con el logo y el contacto, comunes a todas las pantallas."""
    st.markdown(ESTILO, unsafe_allow_html=True)
    st.markdown(
        f"<div class='barra-marca'><img src='{imagen_en_linea('logo_horizontal.png')}' "
        f"alt='Vika Sports, gimnasia rítmica'>"
        f"<a class='whatsapp' href='{WHATSAPP_ENLACE}' target='_blank' rel='noopener' "
        f"aria-label='Contacto por WhatsApp: {WHATSAPP_NUMERO}'>"
        f"<span class='icono'>{ICONO_WHATSAPP}</span>"
        f"<span class='texto'><small>Contacto</small><b>{WHATSAPP_NUMERO}</b></span></a></div>",
        unsafe_allow_html=True,
    )


def mostrar_html(codigo):
    """Muestra HTML propio. Quita la sangría para que no se interprete como bloque de código."""
    st.markdown("".join(linea.strip() for linea in codigo.splitlines()), unsafe_allow_html=True)


def paso(numero, titulo, texto):
    st.markdown(
        f"<div class='paso'><span class='num'>{numero}</span>"
        f"<div><h3>{titulo}</h3><p>{texto}</p></div></div>",
        unsafe_allow_html=True,
    )


def con_precio(opciones):
    if es_recorte():
        return lambda o: o  # con recorte no se muestran precios
    return lambda o: f"{o} · +{euros(opciones[o])}" if opciones.get(o) else o


def tarjeta_resumen(lineas, unidad, cantidad, total, extras=(), consultar=False):
    lineas = list(lineas) + [(f"Extra · {c}", p) for c, p in extras]
    precio_extras = sum(p for _, p in extras)
    if consultar:
        # Recorte: se listan las opciones elegidas, sin precios.
        lineas = [(c, None) for c, _ in lineas if c != "Precio base"]
    if lineas:
        filas = "".join(
            f"<li><span>{html.escape(c)}</span><span>{'' if p is None else euros(p)}</span></li>" for c, p in lineas
        )
        cuerpo = f"<ul>{filas}</ul>"
    else:
        cuerpo = "<div class='vacio'>Elige las opciones del maillot y aquí verás el precio.</div>"
    if consultar:
        cuentas = f"""
      <div class="cuentas"><span>Cantidad</span><span>× {cantidad}</span></div>
      <div class="total"><b>Precio</b><strong style="font-size:1.5rem">Consultar precio</strong></div>"""
    else:
        cuentas = f"""
      <div class="cuentas"><span>Precio por maillot</span><span>{euros(unidad)}</span></div>
      <div class="cuentas"><span>Cantidad</span><span>× {cantidad}</span></div>
      {f'<div class="cuentas"><span>Extras</span><span>+ {euros(precio_extras)}</span></div>' if extras else ''}
      <div class="total"><b>Total</b><strong>{euros(total + precio_extras)}</strong></div>"""
    return f"""
    <div class="resumen ancla-resumen">
      <div class="arriba"><span class="eti">Presupuesto</span><h3>Tu maillot</h3></div>
      {cuerpo}{cuentas}
    </div>"""


def pagina_pedido():
    config = cargar_config()
    modelo_de_enlace()
    mostrar_html(
        f"""<div class="cabecera">{CINTA}
        <span class="etiqueta">Maillots de gimnasia rítmica</span>
        <h1>Diseña tu maillot</h1>
        <p>Toca las opciones que quieras y verás el precio al momento. Solo te lleva un par de minutos.</p>
        </div>"""
    )

    izquierda, derecha = st.columns([5, 3], gap="large")

    with izquierda:
        with st.container(border=True):
            paso(1, "Tus datos", "Para enviarte el presupuesto y confirmar el pedido.")
            st.text_input("Nombre y apellido *", key="nombre", placeholder="Ej.: Laura García")
            a, b = st.columns(2)
            a.text_input("Ciudad *", key="ciudad", placeholder="Ej.: Valencia")
            b.text_input("Club", key="club", placeholder="Ej.: Club Rítmica Infantado")
            a.text_input("Teléfono *", key="telefono", placeholder="Ej.: 600 123 456")
            b.text_input("Email", key="email", placeholder="tu@email.com")

        with st.container(border=True):
            paso(2, "Tu maillot", "Toca una opción en cada grupo.")
            bloque_modelo()
            a, b = st.columns([3, 1])
            a.text_input("Nombre de la gimnasta *", key="gimnasta", placeholder="Ej.: Lucía")
            b.number_input("Cantidad *", min_value=1, step=1, key="cantidad")
            disenos = st.file_uploader(
                "📎 Adjunta la imagen del diseño que te gusta (opcional)", type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True, key=clave_disenos(),
                help="Una foto o captura del maillot o diseño de referencia. Trabajaremos el maillot a partir de ella.",
            )
            if disenos:
                st.image(disenos[:6], width=110)
            st.pills("Producto", config["productos"], key="producto", default=config["productos"][0])
            for grupo in grupos_visibles(config):
                opciones = config["opciones"][grupo]
                if es_varios(config, grupo):
                    st.pills(f"{grupo} (opcional, puedes elegir varios)", list(opciones), key=clave_grupo(grupo),
                             selection_mode="multi", format_func=con_precio(opciones))
                else:
                    st.pills(f"{grupo} *", list(opciones), key=clave_grupo(grupo), format_func=con_precio(opciones))
                if grupo == "Mangas" and una_manga():
                    st.pills("¿En qué brazo va la manga? *", LADOS_MANGA, key="manga_lado")

            if es_recorte():
                st.info("Con la técnica de recorte el maillot se hace a medida y el precio se consulta. "
                        "Te enviaremos el presupuesto.")

            tallaje = elecciones_actuales(config).get("Tallaje")
            if tallaje == "Talla":
                st.pills("Elige la talla *", config["tallas"], key="talla")
            elif tallaje == "A medida":
                st.markdown("**Medidas de la gimnasta, en centímetros**")
                st.toggle("Es un mono (con piernas)", key="es_mono")
                for bloque in medidas_visibles():
                    st.markdown(f"*{bloque}*")
                    cols = st.columns(3)
                    for i, m in enumerate(MEDIDAS[bloque]):
                        cols[i % 3].number_input(m, min_value=0.0, step=0.5, value=None, key="m_" + m,
                                                 placeholder="cm")

        if config.get("extras"):
            with st.container(border=True):
                paso(3, "Extras", "Opcional. Pedrería para decorar el maillot.")
                for grupo, datos in config["extras"].items():
                    opciones = datos["opciones"]
                    if datos.get("por_unidad"):
                        st.markdown(f"**{grupo}** · precio por piedra, escribe cuántas quieres")
                        cols = st.columns(len(opciones))
                        for col, (opcion, precio) in zip(cols, opciones.items()):
                            col.number_input(f"{opcion} · {euros(precio)}/ud.", min_value=0, step=10, value=0,
                                             key=clave_extra(grupo, opcion))
                    else:
                        st.pills(grupo, list(opciones), key=clave_extra(grupo),
                                 format_func=lambda o, op=opciones: f"{o} · {euros(op[o])}")
                    if grupo == "Piedras de coser de plástico" and config.get("nota_piedras"):
                        st.info(config["nota_piedras"], icon="🪡")

        with st.container(border=True):
            paso(4 if config.get("extras") else 3, "Detalles", "Opcional. Cuéntanos qué más necesitas.")
            st.text_area("Complementos por presupuestar", key="complementos", height=100,
                         placeholder="Toca aquí y escribe los complementos que quieres. Ej.: scrunchie a juego, funda…",
                         help="Te enviaremos el precio de los complementos aparte.")
            st.text_area("Descripción y observaciones", key="descripcion", height=130,
                         placeholder="Toca aquí y escribe cómo imaginas el maillot: colores, estampado, pedrería, música…")

    with derecha:
        elecciones = elecciones_actuales(config)
        cantidad = st.session_state.get("cantidad", 1)
        lineas, unidad, total = calcular(config, elecciones, cantidad)
        mostrar_html(tarjeta_resumen(lineas, unidad, cantidad, total, extras_elegidos(config), consultar=es_recorte()))

        faltan = datos_que_faltan(config)
        necesarios = len(requisitos(config))
        hechos = necesarios - len(faltan)
        st.progress(hechos / necesarios,
                    text="¡Todo listo para enviar!" if not faltan else f"Te faltan {len(faltan)} datos obligatorios")
        st.button("Enviar pedido", type="primary", width="stretch",
                  on_click=enviar_pedido, args=(config,))
        st.markdown("<p class='nota'>Precio orientativo. Los complementos se confirman aparte.</p>",
                    unsafe_allow_html=True)

        aviso = st.session_state.pop("aviso", None)
        if aviso:
            if aviso[0] == "ok":
                st.success(aviso[1], icon="🎉")
                st.balloons()
                resumen = st.session_state.pop("ultimo_pedido", "")
                if resumen:
                    st.markdown("**Último paso: mándanos el pedido por WhatsApp** para que lo veamos al momento.")
                    st.link_button("Enviar mi pedido por WhatsApp", type="primary", width="stretch",
                                   url=f"{WHATSAPP_ENLACE}?text={urllib.parse.quote(resumen)}")
                    with st.expander("Ver el resumen de mi pedido", expanded=True):
                        st.text(resumen.replace("*", ""))
            else:
                st.error(aviso[1])


# ---------------------------------------------------------------- página: base de datos

# Columnas por las que se puede filtrar, con su nombre visible.
FILTROS = {
    "ciudad": "Ciudad", "club": "Club", "producto": "Producto", "tecnica": "Técnica",
    "diseno": "Diseño", "forro": "Forro", "tejido": "Tejido", "falda": "Falda", "mangas": "Mangas",
    "tallaje": "Tallaje", "talla": "Talla", "estado": "Estado",
}
NOMBRES = {
    "id": "N.º", "fecha": "Fecha", "estado": "Estado", "nombre": "Cliente", "ciudad": "Ciudad",
    "club": "Club", "telefono": "Teléfono", "email": "Email", "producto": "Producto",
    "cantidad": "Cant.", "gimnasta": "Gimnasta", "tecnica": "Técnica", "diseno": "Diseño",
    "forro": "Forro", "tejido": "Tejido", "falda": "Falda",
    "mangas": "Mangas", "tallaje": "Tallaje", "talla": "Talla", "medidas": "Medidas", "extras": "Extras", "imagenes": "Imágenes", "modelo": "Modelo de catálogo",
    "complementos": "Complementos", "descripcion": "Descripción y observaciones", "precio_unidad": "Precio/ud.",
    "total": "Total",
}
BUSCAR_EN = ["nombre", "gimnasta", "club", "ciudad", "telefono", "email", "descripcion", "complementos"]


def a_excel(tabla, hoja):
    salida = io.BytesIO()
    tabla.to_excel(salida, index=False, sheet_name=hoja)
    return salida.getvalue()


def filtrar(pedidos):
    with st.container(border=True):
        buscar = st.text_input("Buscar", key="f_buscar",
                               placeholder="Nombre, gimnasta, teléfono, email, descripción…")
        columnas = st.columns(3)
        elegidos = {}
        for i, (col, etiqueta) in enumerate(FILTROS.items()):
            valores = sorted({v for v in pedidos[col].dropna() if str(v).strip()})
            elegidos[col] = columnas[i % 3].multiselect(etiqueta, valores, placeholder="Todos", key="f_" + col)
        dias = pedidos["fecha_dt"].dt.date.dropna()
        rango = st.date_input("Fechas del pedido", value=(dias.min(), dias.max()),
                              format="DD/MM/YYYY", key="f_fechas") if not dias.empty else None

    vista = pedidos
    for col, valores in elegidos.items():
        if valores:
            vista = vista[vista[col].isin(valores)]
    # Con todas las fechas elegidas no se filtra, para no esconder pedidos con la fecha en otro formato.
    if isinstance(rango, (list, tuple)) and len(rango) == 2 and tuple(rango) != (dias.min(), dias.max()):
        dia = vista["fecha_dt"].dt.date
        vista = vista[(dia >= rango[0]) & (dia <= rango[1])]
    if buscar:
        texto = vista[BUSCAR_EN].fillna("").astype(str).agg(" ".join, axis=1)
        vista = vista[texto.str.contains(buscar, case=False, regex=False)]
    return vista


def tabla_clientes(vista):
    """Una fila por cliente. Se reconoce a la misma persona por su teléfono (o su nombre si no lo dio)."""
    v = vista.assign(clave=vista["telefono"].fillna("").str.replace(r"\D", "", regex=True))
    sin_telefono = v["clave"] == ""
    v.loc[sin_telefono, "clave"] = v.loc[sin_telefono, "nombre"].str.lower().str.strip()
    clientes = v.sort_values("fecha_dt").groupby("clave").agg(**{
        "Cliente": ("nombre", "last"),
        "Teléfono": ("telefono", "last"),
        "Email": ("email", "last"),
        "Ciudad": ("ciudad", "last"),
        "Club": ("club", "last"),
        "Gimnastas": ("gimnasta", lambda s: ", ".join(sorted({x for x in s if x}))),
        "Pedidos": ("id", "count"),
        "Maillots": ("cantidad", "sum"),
        "Importe total": ("total", "sum"),
        "Último pedido": ("fecha_dt", "max"),
    })
    return clientes.sort_values("Último pedido", ascending=False).reset_index(drop=True)


COLOR_ESTADO = {
    "Nuevo": "#C0157E", "Presupuesto enviado": "#C46A00", "Confirmado": "#008C93",
    "En confección": "#4F55C2", "Entregado": "#23854A", "Cancelado": "#6F7A7C",
}


def fecha_bonita(fecha):
    try:
        return datetime.strptime(str(fecha), "%Y-%m-%d %H:%M").strftime("%d/%m/%Y · %H:%M")
    except ValueError:
        return str(fecha)


def codigo_modelo(modelo):
    """De «VKS-221 · Nombre» saca «VKS-221»."""
    return str(modelo or "").split(" · ")[0].strip()


def whatsapp_cliente(telefono):
    numero = "".join(c for c in str(telefono) if c.isdigit())
    if len(numero) == 9:
        numero = "34" + numero
    return f"https://wa.me/{numero}" if numero else ""


def partes_medidas(medidas):
    """Las medidas guardadas («Cuerpo: Pecho 80 cm, Cintura -; Manga: …») como
    [(bloque, [(medida, cifra), …]), …]. Lo que no se reconoce se conserva entero."""
    partes = []
    for bloque in str(medidas or "").split(";"):
        nombre, dos_puntos, valores = bloque.partition(":")
        if not dos_puntos:  # texto con otro formato: se muestra tal cual
            nombre, valores = "", bloque
        casillas = []
        for valor in valores.split(","):
            valor = valor.strip()
            if not valor:
                continue
            medida = next((m for m in sorted(TODAS_LAS_MEDIDAS, key=len, reverse=True) if valor.startswith(m)), None)
            if medida:
                cifra = valor[len(medida):].strip()
                casillas.append((medida, "—" if cifra in ("", "-") else cifra))
            else:  # medida que no se reconoce: se muestra entera, sin perderla
                casillas.append(("", valor))
        if casillas:
            partes.append((nombre.strip(), casillas))
    return partes


# ---------------------------------------------------------------- ficha del pedido (imagen)

FUENTES = CARPETA / "fuentes"
NARANJA = "#E8601C"
ROJO = "#E3000F"
NEGRO = "#151515"
GRIS = "#6F7A7C"
ANCHO_FICHA = 1180


@st.cache_resource
def fuente(archivo, tamano):
    return ImageFont.truetype(str(FUENTES / archivo), tamano)


def letra_mano(tamano):
    return fuente("PatrickHand-Regular.ttf", tamano)


def letra_etiqueta(tamano, grosor="SemiBold"):
    return fuente(f"Montserrat-{grosor}.ttf", tamano)


@st.cache_data(ttl=3600, show_spinner=False)
def foto_catalogo(codigo):
    """Foto de frente del modelo de catálogo, o None si no se puede descargar."""
    try:
        return urllib.request.urlopen(f"{CATALOGO_URL}{codigo}-frente.webp", timeout=15).read()
    except Exception:
        return None


def partir_lineas(dibujo, texto, letra, ancho):
    """Reparte el texto en líneas que caben en el ancho, respetando los saltos de línea."""
    lineas = []
    for parrafo in str(texto).splitlines() or [""]:
        linea = ""
        for palabra in parrafo.split():
            prueba = f"{linea} {palabra}".strip()
            if linea and dibujo.textlength(prueba, font=letra) > ancho:
                lineas.append(linea)
                linea = palabra
            else:
                linea = prueba
        lineas.append(linea)
    return lineas


def escribir(dibujo, texto, x, y, ancho, letra, color, centrado=False, interlineado=1.15):
    """Escribe el texto en varias líneas si hace falta. Devuelve la y de debajo."""
    alto = round(letra.size * interlineado)
    for linea in partir_lineas(dibujo, texto, letra, ancho):
        dx = (ancho - dibujo.textlength(linea, font=letra)) / 2 if centrado else 0
        dibujo.text((x + dx, y), linea, font=letra, fill=color)
        y += alto
    return y


def pegar_foto(lienzo, datos, x, y, ancho, alto):
    """Pega la foto encajada en el recuadro, sin deformarla."""
    try:
        foto = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGBA")
    except Exception:
        return
    foto.thumbnail((ancho, alto))
    lienzo.paste(foto, (x + (ancho - foto.width) // 2, y + (alto - foto.height) // 2), foto)


def flecha(dibujo, cx, cy):
    """Botón azul con flecha, como en las fichas de Vika."""
    dibujo.rounded_rectangle((cx - 32, cy - 32, cx + 32, cy + 32), radius=14, fill="#4A86E8", outline="#2F5FB3", width=3)
    dibujo.polygon([(cx - 18, cy - 8), (cx + 2, cy - 8), (cx + 2, cy - 20), (cx + 22, cy),
                    (cx + 2, cy + 20), (cx + 2, cy + 8), (cx - 18, cy + 8)], fill="white")


def precio_corto(valor):
    """123 → «123€»; 123.5 → «123,50€»."""
    return f"{valor:g}€" if float(valor).is_integer() else euros(valor).replace(" ", "")


def texto_cristales(extras):
    """«Cristales: 1440 cristales (30,00 €); …» → «1440 CRISTALES Y 40 PIEDRAS…», sin los precios."""
    partes = []
    for extra in str(extras or "").split(";"):
        extra = extra.split(" (")[0].strip()
        if extra:
            grupo, dos_puntos, opcion = extra.partition(": ")
            if not dos_puntos:  # «Piedras de coser de cristal básicas × 20»
                partes.append(extra)
            elif "piedra" in opcion.lower() and "piedra" in grupo.lower():
                partes.append(f"{opcion} {grupo.lower().removeprefix('piedras').strip()}")
            else:
                partes.append(opcion)
    return " y ".join(partes).upper()


def ficha_imagen(p, fotos):
    """Ficha del pedido con el diseño de Vika Sports, en PNG.
    Arriba, como la ficha de taller; debajo, el resto de datos para no perder nada."""
    lienzo = Image.new("RGB", (ANCHO_FICHA, 6000), "white")
    d = ImageDraw.Draw(lienzo)

    # Cabecera: degradado rosa-turquesa con el logo
    for x in range(ANCHO_FICHA):
        t = x / ANCHO_FICHA
        d.line([(x, 0), (x, 290)], fill=tuple(round(a + (b - a) * t) for a, b in zip((249, 214, 234), (205, 239, 241))))
    logo = Image.open(IMAGENES / "logo_horizontal.png").convert("RGBA")
    logo.thumbnail((900, 210))
    lienzo.paste(logo, ((ANCHO_FICHA - logo.width) // 2, (290 - logo.height) // 2), logo)

    recorte = p["tecnica"] == "Recorte"
    cantidad = int(float(p["cantidad"] or 0))
    if p["tallaje"] == "A medida":
        tallaje = "MEDIDA"
    elif str(p["talla"]).strip():
        tallaje = f"TALLA {p['talla']}"
    else:
        tallaje = str(p["tallaje"]).upper() or "—"
    telas = "\n".join(x for x in [str(p["tecnica"]).upper(), " · ".join(
        str(v).upper() for v in [p["tejido"], p["forro"]] if str(v).strip())] if x)

    # Columna izquierda: etiquetas en negro y valores en naranja
    izq_x, izq_ancho = 30, 440
    y = 340
    for etiqueta, valor in [("Gimnasta", tallaje), ("Telas y colores:", telas or "—"),
                            ("Falda:", str(p["falda"]).upper() or "—"), ("Manga:", str(p["mangas"]).upper() or "—"),
                            ("Complementos:", str(p["complementos"]).upper() or "SIN COMPLEMENTOS")]:
        y = escribir(d, etiqueta, izq_x, y, izq_ancho, letra_etiqueta(44), NEGRO)
        y = escribir(d, valor, izq_x + 20, y + 8, izq_ancho - 20, letra_mano(46), NARANJA) + 50
    fin_izquierda = y

    # Columna derecha: nombre de la gimnasta, diseño y precio
    der_x, der_ancho = 490, 670
    y = escribir(d, str(p["gimnasta"]).upper() or "—", der_x, 350, der_ancho, letra_mano(66), NARANJA, centrado=True) + 40
    if len(fotos) == 2:
        pegar_foto(lienzo, fotos[0], der_x, y, 300, 500)
        pegar_foto(lienzo, fotos[1], der_x + der_ancho - 300, y, 300, 500)
        flecha(d, der_x + der_ancho // 2, y + 250)
        y += 540
    elif fotos:
        # Una foto grande, o de dos en dos si hay más
        alto = 520 if len(fotos) == 1 else 400
        for i in range(0, len(fotos), 2):
            fila = fotos[i:i + 2]
            ancho = der_ancho // len(fila)
            for j, foto in enumerate(fila):
                pegar_foto(lienzo, foto, der_x + j * ancho + 8, y, ancho - 16, alto)
            y += alto + 20
        y += 20
    else:
        d.rounded_rectangle((der_x + 60, y, der_x + der_ancho - 60, y + 300), radius=24, outline="#DCECEE", width=4)
        escribir(d, "Sin foto ni modelo de catálogo", der_x + 60, y + 125, der_ancho - 120, letra_etiqueta(28), GRIS,
                 centrado=True)
        y += 340
    etiqueta_pvp, letra_pvp = "P.V.P:", letra_etiqueta(84, "ExtraBold")
    valor_pvp = "CONSULTAR" if recorte else precio_corto(float(p["total"] or 0))
    letra_valor = letra_mano(72 if recorte else 140)
    ancho_pvp = d.textlength(etiqueta_pvp, font=letra_pvp) + 30 + d.textlength(valor_pvp, font=letra_valor)
    px = der_x + (der_ancho - ancho_pvp) / 2
    d.text((px, y + 40), etiqueta_pvp, font=letra_pvp, fill=ROJO)
    d.text((px + d.textlength(etiqueta_pvp, font=letra_pvp) + 30, y + (40 if recorte else 0)), valor_pvp,
           font=letra_valor, fill=NARANJA)
    y += 170
    if not recorte and cantidad > 1:
        y = escribir(d, f"{cantidad} maillots × {precio_corto(float(p['precio_unidad'] or 0))}", der_x, y, der_ancho,
                     letra_etiqueta(30), GRIS, centrado=True)
    fin_derecha = y

    # Descripción y cristales
    y = max(fin_izquierda, fin_derecha) + 40
    fin_desc = escribir(d, "Descripción:", izq_x, y, izq_ancho + 20, letra_etiqueta(48), NEGRO, centrado=True)
    fin_desc = escribir(d, str(p["descripcion"]).upper() or "—", izq_x, fin_desc + 50, izq_ancho + 20, letra_mano(46),
                        NARANJA, centrado=True)
    fin_cris = escribir(d, "Cristales:", der_x, y, der_ancho, letra_etiqueta(48), NEGRO, centrado=True)
    fin_cris = escribir(d, texto_cristales(p["extras"]) or "SIN CRISTALES", der_x, fin_cris + 30, der_ancho,
                        letra_mano(56), NARANJA, centrado=True)
    y = max(fin_desc, fin_cris) + 60

    # El resto de datos del pedido, para que la ficha lo tenga todo
    d.line([(30, y), (ANCHO_FICHA - 30, y)], fill="#DCECEE", width=3)
    y += 30
    numero = int(p["id"])
    filas = [
        ("Pedido", f"N.º {numero} · {fecha_bonita(p['fecha'])} · {p['estado']}"),
        ("Cliente", p["nombre"]), ("Teléfono", p["telefono"]), ("Email", p["email"]),
        ("Club", p["club"]), ("Ciudad", p["ciudad"]), ("Producto", p["producto"]), ("Cantidad", cantidad),
        ("Diseño", p["diseno"]), ("Modelo", p["modelo"]),
        ("Precio", "Consultar (recorte)" if recorte else
         f"{euros(float(p['precio_unidad'] or 0))} por maillot · Total {euros(float(p['total'] or 0))}"),
        ("Extras", "\n".join(e.strip() for e in str(p["extras"]).split(";") if e.strip())),
        ("Imágenes", p["imagenes"]),
        # Datos de columnas de versiones anteriores del formulario, para no perder nada.
        *[(c.replace("_", " ").capitalize(), v) for c, v in p.items() if c not in COLUMNAS and c != "fecha_dt"],
    ]
    for etiqueta, valor in filas:
        if str(valor).strip():
            d.text((40, y), etiqueta, font=letra_etiqueta(26), fill=GRIS)
            if d.textlength(etiqueta, font=letra_etiqueta(26)) > 195:  # nombre largo: el valor va debajo
                y += 36
            y = escribir(d, valor, 250, y, ANCHO_FICHA - 290, letra_etiqueta(26, "Bold"), NEGRO, interlineado=1.3) + 8

    medidas = partes_medidas(p["medidas"])
    if medidas:
        y += 20
        d.text((40, y), "Medidas (cm)", font=letra_etiqueta(30, "Bold"), fill=NEGRO)
        y += 50
        for bloque, casillas in medidas:
            if bloque:
                d.text((40, y), bloque, font=letra_etiqueta(26, "Bold"), fill="#C0157E")
                y += 40
            for i, (medida, cifra) in enumerate(casillas):
                cx, cy = 40 + (i % 5) * 222, y + (i // 5) * 100
                d.rounded_rectangle((cx, cy, cx + 206, cy + 86), radius=14, fill="#E3F6F7")
                d.text((cx + 14, cy + 10), medida, font=letra_etiqueta(22), fill=GRIS)
                d.text((cx + 14, cy + 40), cifra, font=letra_etiqueta(30, "Bold"), fill=NEGRO)
            y += ((len(casillas) - 1) // 5 + 1) * 100 + 10
    y += 40

    salida = io.BytesIO()
    lienzo.crop((0, 0, ANCHO_FICHA, y)).save(salida, "PNG", optimize=True)
    return salida.getvalue()


def guardar_estado_ficha(numero, clave):
    estado = st.session_state[clave]
    cambiar_estado(numero, estado)
    st.toast(f"Pedido n.º {numero}: {estado}")


def fotos_del_pedido(p):
    """Foto del modelo de catálogo (si se puede descargar) y las imágenes que adjuntó el cliente."""
    codigo = codigo_modelo(p["modelo"])
    imagenes = leer_imagenes(int(p["id"]))
    return [f for f in [foto_catalogo(codigo) if codigo else None] if f] + [foto for _, foto in imagenes], imagenes


def nombre_ficha(p):
    return f"ficha-pedido-{int(p['id'])}-{str(p['gimnasta']).strip().replace(' ', '-') or 'maillot'}.png"


def todas_las_fichas(vista):
    """ZIP con la ficha de cada pedido en PNG y un PDF con todas, una por página.
    Solo lee los pedidos: no cambia nada en la base de datos."""
    salida, paginas, fallos = io.BytesIO(), [], []
    avance = st.progress(0.0, text="Preparando fichas…")
    filas = vista.fillna("").to_dict("records")
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zip_fichas:
        for i, p in enumerate(filas, 1):
            try:
                ficha = ficha_imagen(p, fotos_del_pedido(p)[0])
                zip_fichas.writestr(nombre_ficha(p), ficha)
                paginas.append(Image.open(io.BytesIO(ficha)).convert("RGB"))
            except Exception as error:  # se avisa del pedido que falle, nunca se salta en silencio
                fallos.append(f"Pedido n.º {p['id']}: {error}")
            avance.progress(i / len(filas), text=f"Ficha {i} de {len(filas)}")
        if paginas:
            pdf = io.BytesIO()
            paginas[0].save(pdf, "PDF", save_all=True, append_images=paginas[1:], resolution=150)
            zip_fichas.writestr("todas-las-fichas.pdf", pdf.getvalue())
        if fallos:
            zip_fichas.writestr("PEDIDOS-SIN-FICHA.txt", "\n".join(fallos))
    avance.empty()
    return salida.getvalue(), len(paginas), fallos


def bloque_todas_las_fichas(vista):
    with st.container(border=True):
        st.markdown(f"**Fichas de todos los pedidos de la lista ({len(vista)})**")
        st.caption("Descarga un ZIP con la ficha de cada pedido en imagen y un PDF con todas, para imprimir. "
                   "Solo se leen los pedidos: no se cambia ni se borra nada.")
        pedidos_lista = tuple(vista["id"])
        if st.button("Preparar las fichas", key="preparar_fichas"):
            st.session_state.fichas_zip = (pedidos_lista, todas_las_fichas(vista))
        # Si cambian los filtros, el ZIP anterior ya no corresponde a la lista: se vuelve a preparar.
        guardado = st.session_state.get("fichas_zip")
        if guardado and guardado[0] == pedidos_lista:
            datos, hechas, fallos = guardado[1]
            if fallos:
                st.error(f"{len(fallos)} pedido(s) no se pudieron pasar a ficha (sus datos siguen intactos):\n\n"
                         + "\n".join(f"- {f}" for f in fallos))
            st.success(f"{hechas} fichas listas.")
            st.download_button("⬇️ Descargar todas las fichas (ZIP)", datos, type="primary",
                               file_name=f"fichas-pedidos-{ahora():%Y-%m-%d}.zip", mime="application/zip")


def ficha_pedido(p, donde):
    """Ficha completa de un pedido, con el diseño de las fichas de Vika Sports."""
    numero = int(p["id"])
    recorte = p["tecnica"] == "Recorte"
    color = COLOR_ESTADO.get(p["estado"], "#C0157E")
    lugar = " · ".join(x for x in [p["club"], p["ciudad"]] if str(x).strip())
    importe = "Consultar precio" if recorte else euros(float(p["total"] or 0))
    st.markdown(
        f"<div class='ficha-cab'><div>"
        f"<span class='eti'>Pedido n.º {numero} · {html.escape(fecha_bonita(p['fecha']))}</span>"
        f"<h2>{html.escape(p['nombre'])}</h2><span class='sub'>{html.escape(lugar)}</span></div>"
        f"<div class='importe'><span class='chip-estado' style='color:{color}'>{html.escape(p['estado'])}</span>"
        f"<strong>{importe}</strong></div></div>",
        unsafe_allow_html=True,
    )

    a, b, c = st.columns([2, 1, 1], vertical_alignment="bottom")
    a.selectbox("Estado del pedido", ESTADOS, key=f"estado_ficha_{donde}_{numero}",
                index=ESTADOS.index(p["estado"]) if p["estado"] in ESTADOS else 0,
                on_change=guardar_estado_ficha, args=(numero, f"estado_ficha_{donde}_{numero}"))
    enlace = whatsapp_cliente(p["telefono"])
    if enlace:
        b.link_button("WhatsApp al cliente", enlace, width="stretch")
    if p["email"]:
        c.link_button("Email al cliente", f"mailto:{p['email']}?subject=" + urllib.parse.quote(f"Tu pedido n.º {numero} de Vika Sports"),
                      width="stretch")

    codigo = codigo_modelo(p["modelo"])
    fotos, imagenes = fotos_del_pedido(p)
    ficha = ficha_imagen(p, fotos)

    izquierda, derecha = st.columns([3, 2], gap="large")
    with izquierda:
        st.image(ficha, width="stretch")
    with derecha:
        st.download_button("⬇️ Descargar ficha (imagen)", ficha, file_name=nombre_ficha(p), mime="image/png",
                           type="primary", key=f"ficha_{donde}_{numero}", width="stretch")
        st.caption("La imagen lleva todos los datos del pedido. Puedes mandarla por WhatsApp o imprimirla.")
        if codigo:
            st.link_button("Ver el modelo en el catálogo", f"{CATALOGO_URL}#{codigo}", width="stretch")
            if foto_catalogo(codigo) is None:
                st.caption("No se pudo cargar la foto del modelo de catálogo.")
        for i, (nombre, foto) in enumerate(imagenes):
            st.download_button(f"Descargar diseño del cliente: {nombre}", foto, file_name=f"pedido-{numero}-{nombre}",
                               mime="image/jpeg", key=f"img_{donde}_{numero}_{i}", width="stretch")
        if not imagenes and str(p["imagenes"]).strip():
            st.caption(f"El cliente adjuntó: {p['imagenes']} (la imagen no está guardada en la base de datos).")
        with st.expander("Texto del pedido para copiar"):
            st.code(texto_pedido(numero, p).replace("*", ""), language=None)


def pestana_tabla_completa(vista):
    """Todos los campos de los pedidos. El estado se puede cambiar en la columna Estado."""
    config_columnas = {c: st.column_config.Column(NOMBRES[c]) for c in COLUMNAS}
    config_columnas.update({
        "id": st.column_config.NumberColumn("N.º", width="small"),
        "estado": st.column_config.SelectboxColumn("Estado", options=ESTADOS, required=True),
        "precio_unidad": st.column_config.NumberColumn("Precio/ud.", format="%.2f €"),
        "total": st.column_config.NumberColumn("Total", format="%.2f €"),
    })
    editada = st.data_editor(
        vista, hide_index=True, width="stretch", column_order=COLUMNAS,
        disabled=[c for c in vista.columns if c != "estado"],
        column_config=config_columnas, key="tabla_pedidos",
    )
    cambios = editada[editada["estado"] != vista["estado"]]
    for _, fila in cambios.iterrows():
        cambiar_estado(int(fila["id"]), fila["estado"])
    if not cambios.empty:
        st.toast(f"Estado actualizado en {len(cambios)} pedido(s).")
    st.download_button("Descargar estos pedidos en Excel",
                       a_excel(vista.drop(columns="fecha_dt").rename(columns=NOMBRES), "Pedidos"),
                       file_name=f"pedidos-maillots-{ahora():%Y-%m-%d}.xlsx")


def abrir_desde_lista(lista, clave):
    """Al marcar un pedido en la lista, se abre su ficha."""
    filas = st.session_state["lista_pedidos"].selection.rows
    if filas and filas[0] < len(lista):
        st.session_state[clave] = int(lista.iloc[filas[0]]["id"])


def elegir_y_mostrar_ficha(vista, clave):
    """Desplegable con los pedidos de la vista y la ficha del elegido (el más reciente al principio)."""
    if vista.empty:
        st.info("No hay pedidos con estos filtros.")
        return
    pedidos = {int(p["id"]): p for p in vista.fillna("").to_dict("records")}
    if st.session_state.get(clave) not in pedidos:  # el pedido abierto ya no está en la lista (búsqueda, filtros)
        st.session_state[clave] = next(iter(pedidos))
    numero = st.selectbox(
        "Abrir la ficha del pedido", list(pedidos), key=clave,
        format_func=lambda n: " · ".join(str(x) for x in [f"N.º {n}", pedidos[n]["nombre"], pedidos[n]["gimnasta"],
                                                          fecha_bonita(pedidos[n]["fecha"])] if str(x).strip()),
    )
    ficha_pedido(pedidos[numero], clave)


def pagina_base_datos():
    if not acceso_gestion():
        return
    menu_gestion()
    st.title("Base de datos")
    pedidos = leer_pedidos()
    if pedidos.empty:
        st.info("Todavía no hay pedidos. Cada vez que alguien rellene el formulario, se guardará aquí.")
        return

    vista = filtrar(pedidos)
    clientes = tabla_clientes(vista)
    a, b, c, d = st.columns(4)
    a.metric("Pedidos", len(vista))
    b.metric("Clientes", len(clientes))
    c.metric("Maillots", int(vista["cantidad"].sum()))
    d.metric("Importe", euros(vista["total"].sum()))
    if len(vista) < len(pedidos):
        st.caption(f"Mostrando {len(vista)} de {len(pedidos)} pedidos según los filtros.")

    pestana_pedidos, pestana_clientes, pestana_resumen = st.tabs(["Pedidos", "Clientes", "Resumen"])

    with pestana_pedidos:
        bloque_todas_las_fichas(vista)
        st.caption("Marca la casilla de la izquierda de un pedido, o elígelo debajo, para abrir su ficha.")
        lista = vista[["id", "fecha", "estado", "nombre", "club", "gimnasta", "modelo", "total"]].reset_index(drop=True)
        st.dataframe(
            lista, hide_index=True, width="stretch", selection_mode="single-row",
            on_select=lambda: abrir_desde_lista(lista, "ficha_abierta"),
            key="lista_pedidos", height=min(38 + 35 * len(lista), 320),
            column_config={
                "id": st.column_config.NumberColumn("N.º", width="small"),
                "fecha": "Fecha", "estado": "Estado", "nombre": "Cliente", "club": "Club",
                "gimnasta": "Gimnasta", "modelo": "Modelo de catálogo",
                "total": st.column_config.NumberColumn("Total", format="%.2f €"),
            },
        )
        elegir_y_mostrar_ficha(vista, "ficha_abierta")

        with st.expander("Tabla completa: cambiar estados de varios pedidos y descargar Excel"):
            pestana_tabla_completa(vista)

    with pestana_clientes:
        st.dataframe(
            clientes, hide_index=True, width="stretch",
            column_config={
                "Importe total": st.column_config.NumberColumn(format="%.2f €"),
                "Último pedido": st.column_config.DatetimeColumn(format="DD/MM/YYYY"),
            },
        )
        st.download_button("Descargar clientes en Excel", a_excel(clientes, "Clientes"),
                           file_name=f"clientes-maillots-{ahora():%Y-%m-%d}.xlsx")
        elegido = st.selectbox("Ver los pedidos de", clientes["Cliente"], index=None,
                               placeholder="Elige un cliente")
        if elegido:
            suyos = vista[vista["nombre"] == elegido]
            st.dataframe(suyos[COLUMNAS].rename(columns=NOMBRES), hide_index=True, width="stretch")
            elegir_y_mostrar_ficha(suyos, "ficha_cliente")

    with pestana_resumen:
        st.caption("Cuántos maillots se han pedido de cada tipo, con los filtros aplicados.")
        columnas = st.columns(2)
        for i, col in enumerate(["ciudad", "tecnica", "diseno", "forro", "tejido", "falda", "mangas", "tallaje", "producto"]):
            conteo = (vista[vista[col].fillna("") != ""].groupby(col)["cantidad"].sum()
                      .sort_values(ascending=False).rename("Maillots"))
            with columnas[i % 2]:
                st.markdown(f"**{NOMBRES[col]}**")
                if conteo.empty:
                    st.caption("Sin datos.")
                else:
                    st.bar_chart(conteo, horizontal=True, height=60 + 32 * len(conteo), color="#00B5BE")


# ---------------------------------------------------------------- página: precios

def editor_precios(opciones, clave, paso_precio=0.5):
    """Tabla editable de opciones y precios. Devuelve {opción: precio}."""
    tabla = pd.DataFrame({"Opción": list(opciones), "Precio (€)": list(opciones.values())})
    editada = st.data_editor(
        tabla, hide_index=True, width="stretch", num_rows="dynamic", key=clave,
        column_config={"Precio (€)": st.column_config.NumberColumn(min_value=0, step=paso_precio, format="%.2f €")},
    )
    return {
        str(f["Opción"]).strip(): float(f["Precio (€)"] or 0)
        for _, f in editada.iterrows() if str(f["Opción"] or "").strip()
    }


def pagina_precios():
    if not acceso_gestion():
        return
    config = cargar_config()
    menu_gestion()
    st.title("Precios")
    st.caption("Escribe el precio de cada opción en euros y pulsa Guardar precios. "
               "El formulario de pedido se actualiza al momento. "
               "Con la técnica de recorte no se calcula precio: al cliente le sale «Consultar precio».")

    base = st.number_input("Precio base del maillot (€)", min_value=0.0, step=1.0,
                           value=float(config["precio_base"]),
                           help="Se suma siempre. Déjalo a 0 si el precio sale solo de las opciones.")
    nuevas = {}
    columnas = st.columns(2)
    for i, (grupo, opciones) in enumerate(config["opciones"].items()):
        with columnas[i % 2]:
            st.subheader(grupo)
            nuevas[grupo] = editor_precios(opciones, "precios_" + grupo)

    nuevos_extras = {}
    if config.get("extras"):
        st.header("Extras")
        st.caption("Se suman una vez al total del pedido, no por maillot.")
        columnas = st.columns(2)
        for i, (grupo, datos) in enumerate(config["extras"].items()):
            with columnas[i % 2]:
                st.subheader(grupo + (" (precio por piedra)" if datos.get("por_unidad") else ""))
                nuevos_extras[grupo] = {**datos, "opciones": editor_precios(datos["opciones"], "extras_" + grupo, 0.05)}
        nota = st.text_input("Nota de las piedras de coser", value=config.get("nota_piedras", ""))

    if st.button("Guardar precios", type="primary"):
        config["precio_base"] = base
        config["opciones"] = nuevas
        if config.get("extras"):
            config["extras"] = nuevos_extras
            config["nota_piedras"] = nota
        guardar_config(config)
        st.success("Precios guardados.")


# ---------------------------------------------------------------- arranque

st.set_page_config(page_title="Vika Sports · Diseña tu maillot", page_icon=str(IMAGENES / "logo_simbolo.png"),
                   layout="wide", initial_sidebar_state="collapsed")
mostrar_marca()
PAGINA_PEDIDO = st.Page(pagina_pedido, title="Nuevo pedido", default=True)
PAGINA_BASE_DATOS = st.Page(pagina_base_datos, title="Base de datos", url_path="base-de-datos")
PAGINA_PRECIOS = st.Page(pagina_precios, title="Precios", url_path="precios")
# El menú va oculto para que los clientes solo vean el formulario.
# Vika Sports entra a gestión con la dirección directa: .../base-de-datos y .../precios
navegacion = st.navigation([PAGINA_PEDIDO, PAGINA_BASE_DATOS, PAGINA_PRECIOS], position="hidden")
navegacion.run()
