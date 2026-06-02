from io import BytesIO
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Prode Mundial - Probabilidades", layout="wide")

FUENTE_OFICIAL_FIFA = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"
OPENFOOTBALL_JSON = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"

st.title("⚽ Prode Mundial - Cruces + Probabilidades")
st.caption("Carga cruces desde fuente pública y calcula probabilidades reales desde cuotas 1X2.")


def cuotas_a_probabilidades(c_local, c_empate, c_visitante):
    vals = [c_local, c_empate, c_visitante]
    if any(v is None or v <= 1 for v in vals):
        return None
    brutas = [1 / v for v in vals]
    total = sum(brutas)
    reales = [b / total for b in brutas]
    margen = total - 1
    return reales[0], reales[1], reales[2], margen


def confianza(max_prob):
    if max_prob >= 0.58:
        return "Alta"
    if max_prob >= 0.46:
        return "Media"
    return "Baja"


def sugerir_resultado(prob_local, prob_empate, prob_visitante):
    # Modelo simple para prode: NO es predicción exacta, traduce tendencia 1X2 a marcador probable.
    if prob_empate >= max(prob_local, prob_visitante):
        return "1-1"
    favorito = "local" if prob_local > prob_visitante else "visitante"
    diferencia = abs(prob_local - prob_visitante)
    if favorito == "local":
        if diferencia >= 0.35:
            return "2-0"
        if diferencia >= 0.18:
            return "2-1"
        return "1-0"
    else:
        if diferencia >= 0.35:
            return "0-2"
        if diferencia >= 0.18:
            return "1-2"
        return "0-1"


@st.cache_data(ttl=3600)
def cargar_mundial_openfootball():
    r = requests.get(OPENFOOTBALL_JSON, timeout=20)
    r.raise_for_status()
    data = r.json()
    rows = []
    for i, m in enumerate(data.get("matches", []), start=1):
        rows.append({
            "id_partido": i,
            "fecha": m.get("date", ""),
            "hora": m.get("time", ""),
            "ronda": m.get("round", ""),
            "grupo": m.get("group", ""),
            "local": m.get("team1", ""),
            "visitante": m.get("team2", ""),
            "sede": m.get("ground", ""),
            "cuota_local": None,
            "cuota_empate": None,
            "cuota_visitante": None,
        })
    return pd.DataFrame(rows)


def preparar_resultados(df):
    out = df.copy()
    cols = ["prob_local", "prob_empate", "prob_visitante", "margen_casa", "recomendacion", "resultado_probable", "confianza"]
    for c in cols:
        if c not in out.columns:
            out[c] = ""

    for idx, row in out.iterrows():
        res = cuotas_a_probabilidades(
            pd.to_numeric(row.get("cuota_local"), errors="coerce"),
            pd.to_numeric(row.get("cuota_empate"), errors="coerce"),
            pd.to_numeric(row.get("cuota_visitante"), errors="coerce"),
        )
        if not res:
            continue
        p1, px, p2, margen = res
        probs = {str(row.get("local", "Local")): p1, "Empate": px, str(row.get("visitante", "Visitante")): p2}
        reco = max(probs, key=probs.get)
        out.at[idx, "prob_local"] = round(p1 * 100, 2)
        out.at[idx, "prob_empate"] = round(px * 100, 2)
        out.at[idx, "prob_visitante"] = round(p2 * 100, 2)
        out.at[idx, "margen_casa"] = round(margen * 100, 2)
        out.at[idx, "recomendacion"] = reco
        out.at[idx, "resultado_probable"] = sugerir_resultado(p1, px, p2)
        out.at[idx, "confianza"] = confianza(max(p1, px, p2))
    return out


def descargar_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Prode")
    output.seek(0)
    return output


with st.sidebar:
    st.header("Fuente de cruces")
    st.write("Fuente oficial para verificar fixture:")
    st.link_button("Abrir FIFA", FUENTE_OFICIAL_FIFA)
    st.write("Fuente abierta usada por la app:")
    st.link_button("Abrir JSON OpenFootball", OPENFOOTBALL_JSON)
    st.info("Las cuotas se cargan manualmente por ahora. Después podemos conectar una API de odds.")

st.subheader("1) Cargar cruces")
col_a, col_b = st.columns([1, 1])

with col_a:
    if st.button("Cargar Mundial 2026 desde OpenFootball", type="primary"):
        st.session_state["partidos"] = cargar_mundial_openfootball()
        st.success("Cruces cargados.")

with col_b:
    archivo = st.file_uploader("O subir CSV/Excel propio", type=["csv", "xlsx"])
    if archivo:
        if archivo.name.lower().endswith(".csv"):
            st.session_state["partidos"] = pd.read_csv(archivo)
        else:
            st.session_state["partidos"] = pd.read_excel(archivo)
        st.success("Archivo cargado.")

if "partidos" not in st.session_state:
    st.warning("Primero cargá los cruces.")
    st.stop()

st.subheader("2) Completar cuotas")
st.caption("Editá cuota local, empate y visitante. La app calcula probabilidades quitando el margen de la casa.")

base = st.session_state["partidos"].copy()
columnas_necesarias = ["cuota_local", "cuota_empate", "cuota_visitante"]
for c in columnas_necesarias:
    if c not in base.columns:
        base[c] = None

editado = st.data_editor(
    base,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "cuota_local": st.column_config.NumberColumn("Cuota local", min_value=1.01, step=0.01, format="%.2f"),
        "cuota_empate": st.column_config.NumberColumn("Cuota empate", min_value=1.01, step=0.01, format="%.2f"),
        "cuota_visitante": st.column_config.NumberColumn("Cuota visitante", min_value=1.01, step=0.01, format="%.2f"),
    },
)

st.session_state["partidos"] = editado
resultado = preparar_resultados(editado)

st.subheader("3) Recomendación para el prode")
cols_show = [
    "fecha", "hora", "ronda", "grupo", "local", "visitante", "sede",
    "cuota_local", "cuota_empate", "cuota_visitante",
    "prob_local", "prob_empate", "prob_visitante", "recomendacion", "resultado_probable", "confianza", "margen_casa"
]
cols_show = [c for c in cols_show if c in resultado.columns]
st.dataframe(resultado[cols_show], use_container_width=True)

st.download_button(
    "Descargar Excel con recomendaciones",
    data=descargar_excel(resultado),
    file_name="prode_mundial_recomendaciones.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()
st.subheader("Notas")
st.write("- La recomendación sale de cuotas 1X2. No garantiza resultado exacto.")
st.write("- Para mejorar el marcador probable después agregamos Over/Under, ambos marcan y ranking FIFA/Elo.")
st.write("- Mejor cargar cuotas de varias casas y promediar, porque una sola fuente puede tener sesgo o margen alto.")
