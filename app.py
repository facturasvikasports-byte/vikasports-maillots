"""Programa de pedidos de maillots de gimnasia rítmica.

Para abrirlo: doble clic en "Abrir programa.bat", o en una terminal:
    .venv\\Scripts\\streamlit run app.py
"""

import base64
import hmac
import html
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, inspect, text

CARPETA = Path(__file__).parent
ARCHIVO_PRECIOS = CARPETA / "precios.json"
BASE_DATOS = CARPETA / "pedidos.db"
IMAGENES = CARPETA / "imagenes"

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
    "producto", "cantidad", "gimnasta", "tecnica", "diseno", "forro", "tejido", "falda", "mangas", "tallaje",
    "talla", "medidas", "complementos", "descripcion", "precio_unidad", "total",
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

@media (max-width: 640px) {
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


@st.cache_resource
def motor():
    """Conexión a la base de datos: Supabase en internet, o el archivo pedidos.db en tu ordenador."""
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
                gimnasta TEXT, tecnica TEXT, diseno TEXT, forro TEXT, tejido TEXT, falda TEXT, mangas TEXT, tallaje TEXT,
                talla TEXT, medidas TEXT, complementos TEXT, descripcion TEXT,
                precio_unidad {decimal}, total {decimal}
            )"""))
        con.execute(text("CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)"))
        if postgres:
            # En Supabase: nadie más que el programa puede leer o cambiar estas tablas.
            con.execute(text("ALTER TABLE pedidos ENABLE ROW LEVEL SECURITY"))
            con.execute(text("ALTER TABLE configuracion ENABLE ROW LEVEL SECURITY"))
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
            valor = archivo
            con.execute(text("UPDATE configuracion SET valor = :v WHERE clave = 'precios'"), {"v": valor})
    return json.loads(valor)


def guardar_config(config):
    valor = json.dumps(config, ensure_ascii=False, indent=2)
    with motor().begin() as con:
        con.execute(text("UPDATE configuracion SET valor = :v WHERE clave = 'precios'"), {"v": valor})
    if not secreto("DATABASE_URL"):
        ARCHIVO_PRECIOS.write_text(valor, encoding="utf-8")  # copia local de los precios
    cargar_config.clear()


def guardar_pedido(pedido):
    campos = [c for c in COLUMNAS if c != "id"]
    with motor().begin() as con:
        return con.execute(
            text(f"INSERT INTO pedidos ({', '.join(campos)}) VALUES ({', '.join(':' + c for c in campos)}) RETURNING id"),
            {c: pedido[c] for c in campos},
        ).scalar()


def leer_pedidos():
    with motor().connect() as con:
        pedidos = pd.read_sql_query(text(f"SELECT {', '.join(COLUMNAS)} FROM pedidos ORDER BY id DESC"), con)
    for col in ["cantidad", "precio_unidad", "total"]:
        pedidos[col] = pd.to_numeric(pedidos[col], errors="coerce").fillna(0)
    pedidos["fecha_dt"] = pd.to_datetime(pedidos["fecha"], format="%Y-%m-%d %H:%M", errors="coerce")
    return pedidos


def cambiar_estado(id_pedido, estado):
    with motor().begin() as con:
        con.execute(text("UPDATE pedidos SET estado = :e WHERE id = :i"), {"e": estado, "i": id_pedido})


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


def enviar_pedido(config):
    s = st.session_state
    faltan = datos_que_faltan(config)
    if faltan:
        s.aviso = ("error", "Te falta rellenar: " + ", ".join(faltan) + ".")
        return

    elecciones = elecciones_actuales(config)
    recorte = es_recorte()
    _, unidad, total = calcular(config, elecciones, s.cantidad)
    texto_de = {g: ", ".join(v) if isinstance(v, list) else (v or "") for g, v in elecciones.items()}
    if una_manga():
        texto_de["Mangas"] += f" ({s.manga_lado.lower()})"
    medidas = ""
    if elecciones.get("Tallaje") == "A medida":
        bloques = medidas_visibles()
        medidas = "; ".join(
            f"{b}: " + ", ".join(f"{m} {s.get('m_' + m) or '-'} cm" for m in MEDIDAS[b]) for b in bloques
        )

    pedido = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "estado": "Nuevo",
        **{c: s.get(c, "").strip() for c in TEXTOS},
        "producto": s.get("producto") or "",
        "cantidad": s.cantidad,
        **{col: texto_de.get(grupo, "") for grupo, col in COLUMNA_DE_GRUPO.items()},
        "talla": (s.get("talla") or "") if elecciones.get("Tallaje") == "Talla" else "",
        "medidas": medidas,
        # Con recorte el precio se consulta: se deja en blanco.
        "precio_unidad": None if recorte else unidad,
        "total": None if recorte else total,
    }
    numero = guardar_pedido(pedido)
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


def tarjeta_resumen(lineas, unidad, cantidad, total, consultar=False):
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
      <div class="total"><b>Total</b><strong>{euros(total)}</strong></div>"""
    return f"""
    <div class="resumen ancla-resumen">
      <div class="arriba"><span class="eti">Presupuesto</span><h3>Tu maillot</h3></div>
      {cuerpo}{cuentas}
    </div>"""


def pagina_pedido():
    config = cargar_config()
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
            a, b = st.columns([3, 1])
            a.text_input("Nombre de la gimnasta *", key="gimnasta", placeholder="Ej.: Lucía")
            b.number_input("Cantidad *", min_value=1, step=1, key="cantidad")
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

        with st.container(border=True):
            paso(3, "Detalles", "Opcional. Cuéntanos qué más necesitas.")
            st.text_area("Complementos por presupuestar", key="complementos", height=100,
                         placeholder="Toca aquí y escribe los complementos que quieres. Ej.: scrunchie a juego, funda…",
                         help="Te enviaremos el precio de los complementos aparte.")
            st.text_area("Descripción y observaciones", key="descripcion", height=130,
                         placeholder="Toca aquí y escribe cómo imaginas el maillot: colores, estampado, pedrería, música…")

    with derecha:
        elecciones = elecciones_actuales(config)
        cantidad = st.session_state.get("cantidad", 1)
        lineas, unidad, total = calcular(config, elecciones, cantidad)
        mostrar_html(tarjeta_resumen(lineas, unidad, cantidad, total, consultar=es_recorte()))

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
    "mangas": "Mangas", "tallaje": "Tallaje", "talla": "Talla", "medidas": "Medidas",
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
                              format="DD/MM/YYYY", key="f_fechas")

    vista = pedidos
    for col, valores in elegidos.items():
        if valores:
            vista = vista[vista[col].isin(valores)]
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
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


def pagina_base_datos():
    if not acceso_gestion():
        return
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
        st.caption("Cambia el estado de un pedido directamente en la columna Estado.")
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
                           a_excel(vista[COLUMNAS].rename(columns=NOMBRES), "Pedidos"),
                           file_name=f"pedidos-maillots-{datetime.now():%Y-%m-%d}.xlsx")

    with pestana_clientes:
        st.dataframe(
            clientes, hide_index=True, width="stretch",
            column_config={
                "Importe total": st.column_config.NumberColumn(format="%.2f €"),
                "Último pedido": st.column_config.DatetimeColumn(format="DD/MM/YYYY"),
            },
        )
        st.download_button("Descargar clientes en Excel", a_excel(clientes, "Clientes"),
                           file_name=f"clientes-maillots-{datetime.now():%Y-%m-%d}.xlsx")
        elegido = st.selectbox("Ver los pedidos de", clientes["Cliente"], index=None,
                               placeholder="Elige un cliente")
        if elegido:
            suyos = vista[vista["nombre"] == elegido]
            st.dataframe(suyos[COLUMNAS].rename(columns=NOMBRES), hide_index=True, width="stretch")

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

def pagina_precios():
    if not acceso_gestion():
        return
    config = cargar_config()
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
            tabla = pd.DataFrame({"Opción": list(opciones), "Precio (€)": list(opciones.values())})
            editada = st.data_editor(
                tabla, hide_index=True, width="stretch", num_rows="dynamic", key="precios_" + grupo,
                column_config={"Precio (€)": st.column_config.NumberColumn(min_value=0, step=0.5, format="%.2f €")},
            )
            nuevas[grupo] = {
                str(f["Opción"]).strip(): float(f["Precio (€)"] or 0)
                for _, f in editada.iterrows() if str(f["Opción"] or "").strip()
            }

    if st.button("Guardar precios", type="primary"):
        config["precio_base"] = base
        config["opciones"] = nuevas
        guardar_config(config)
        st.success("Precios guardados.")


# ---------------------------------------------------------------- arranque

st.set_page_config(page_title="Vika Sports · Diseña tu maillot", page_icon=str(IMAGENES / "logo_simbolo.png"),
                   layout="wide", initial_sidebar_state="collapsed")
mostrar_marca()
navegacion = st.navigation({
    "": [st.Page(pagina_pedido, title="Nuevo pedido", default=True)],
    "Gestión": [
        st.Page(pagina_base_datos, title="Base de datos", url_path="base-de-datos"),
        st.Page(pagina_precios, title="Precios", url_path="precios"),
    ],
})
navegacion.run()
