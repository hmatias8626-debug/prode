import streamlit as st
import pandas as pd
import requests
import unicodedata
from io import BytesIO

st.set_page_config(
    page_title="Prode Mundial 2026",
    page_icon="⚽",
    layout="wide"
)

OPENFOOTBALL_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"

SPORT_KEY_MUNDIAL = "soccer_fifa_world_cup"
SPORT_KEY_CAMPEON = "soccer_fifa_world_cup_winner"

TEAM_ALIASES = {
    "usa": "united states",
    "united states of america": "united states",
    "united states": "united states",
    "mexico": "mexico",
    "méxico": "mexico",
    "corea del sur": "south korea",
    "south korea": "south korea",
    "republica checa": "czech republic",
    "czechia": "czech republic",
    "czech republic": "czech republic",
    "bosnia and herzegovina": "bosnia & herzegovina",
    "bosnia & herzegovina": "bosnia & herzegovina",
    "irán": "iran",
    "iran": "iran",
    "alemania": "germany",
    "germany": "germany",
    "españa": "spain",
    "spain": "spain",
    "francia": "france",
    "france": "france",
    "argentina": "argentina",
    "brasil": "brazil",
    "brazil": "brazil",
    "inglaterra": "england",
    "england": "england",
    "portugal": "portugal",
    "italia": "italy",
    "italy": "italy",
    "uruguay": "uruguay",
    "canada": "canada",
    "qatar": "qatar",
    "suiza": "switzerland",
    "switzerland": "switzerland",
}


def normalizar_nombre(nombre):
    if nombre is None:
        return ""
    texto = str(nombre).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace(".", "").replace("-", " ")
    texto = " ".join(texto.split())
    return TEAM_ALIASES.get(texto, texto)


def get_api_key():
    try:
        return st.secrets["ODDS_API_KEY"]
    except Exception:
        return None


@st.cache_data(ttl=3600)
def cargar_fixture_openfootball():
    r = requests.get(OPENFOOTBALL_URL, timeout=25)
    r.raise_for_status()
    data = r.json()

    filas = []
    partido_id = 1

    for ronda in data.get("rounds", []):
        nombre_ronda = ronda.get("name", "")
        for match in ronda.get("matches", []):
            team1 = match.get("team1") or {}
            team2 = match.get("team2") or {}

            local = team1.get("name") if isinstance(team1, dict) else team1
            visitante = team2.get("name") if isinstance(team2, dict) else team2

            filas.append({
                "id_partido": partido_id,
                "fecha": match.get("date", ""),
                "hora": match.get("time", ""),
                "ronda": nombre_ronda,
                "grupo": match.get("group", ""),
                "local": local,
                "visitante": visitante,
                "sede": match.get("stadium", "") or match.get("city", ""),
                "Cuota local": None,
                "Cuota empate": None,
                "Cuota visitante": None,
                "Bookmaker": None,
            })
            partido_id += 1

    return pd.DataFrame(filas)


def consultar_odds(api_key, sport_key, regions, markets="h2h"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    r = requests.get(url, params=params, timeout=30)

    st.session_state["odds_headers"] = {
        "requests_used": r.headers.get("x-requests-used"),
        "requests_remaining": r.headers.get("x-requests-remaining"),
        "requests_last": r.headers.get("x-requests-last"),
    }

    if r.status_code != 200:
        raise Exception(f"Error API {r.status_code}: {r.text}")

    return r.json()


def consultar_deportes(api_key):
    url = "https://api.the-odds-api.com/v4/sports/"
    r = requests.get(url, params={"apiKey": api_key}, timeout=25)
    r.raise_for_status()
    return r.json()


def eventos_a_tabla_odds(eventos, usar_promedio=True):
    filas = []

    for ev in eventos:
        home = ev.get("home_team", "")
        away = ev.get("away_team", "")
        fecha = ev.get("commence_time", "")

        home_key = normalizar_nombre(home)
        away_key = normalizar_nombre(away)

        cuotas_home = []
        cuotas_draw = []
        cuotas_away = []
        bookmakers_usados = []

        for bk in ev.get("bookmakers", []):
            for market in bk.get("markets", []):
                if market.get("key") != "h2h":
                    continue

                outcomes = market.get("outcomes", [])
                precios = {normalizar_nombre(o.get("name")): o.get("price") for o in outcomes}

                ch = precios.get(home_key)
                cd = precios.get("draw") or precios.get("empate")
                ca = precios.get(away_key)

                if ch and cd and ca:
                    cuotas_home.append(float(ch))
                    cuotas_draw.append(float(cd))
                    cuotas_away.append(float(ca))
                    bookmakers_usados.append(bk.get("title", ""))

                if not usar_promedio and ch and cd and ca:
                    break

            if not usar_promedio and cuotas_home:
                break

        if cuotas_home:
            filas.append({
                "api_home": home,
                "api_away": away,
                "api_fecha": fecha,
                "Cuota local API": round(sum(cuotas_home) / len(cuotas_home), 2),
                "Cuota empate API": round(sum(cuotas_draw) / len(cuotas_draw), 2),
                "Cuota visitante API": round(sum(cuotas_away) / len(cuotas_away), 2),
                "Bookmaker": "Promedio" if usar_promedio and len(bookmakers_usados) > 1 else bookmakers_usados[0],
                "Cantidad bookmakers": len(bookmakers_usados),
            })

    return pd.DataFrame(filas)


def conectar_fixture_con_odds(df_fixture, df_odds):
    if df_fixture.empty or df_odds.empty:
        return df_fixture

    df = df_fixture.copy()

    df["local_norm"] = df["local"].apply(normalizar_nombre)
    df["visitante_norm"] = df["visitante"].apply(normalizar_nombre)

    odds = df_odds.copy()
    odds["home_norm"] = odds["api_home"].apply(normalizar_nombre)
    odds["away_norm"] = odds["api_away"].apply(normalizar_nombre)

    for idx, row in df.iterrows():
        local = row["local_norm"]
        visitante = row["visitante_norm"]

        match = odds[(odds["home_norm"] == local) & (odds["away_norm"] == visitante)]
        invertido = False

        if match.empty:
            match = odds[(odds["home_norm"] == visitante) & (odds["away_norm"] == local)]
            invertido = not match.empty

        if not match.empty:
            m = match.iloc[0]
            if invertido:
                df.at[idx, "Cuota local"] = m["Cuota visitante API"]
                df.at[idx, "Cuota empate"] = m["Cuota empate API"]
                df.at[idx, "Cuota visitante"] = m["Cuota local API"]
            else:
                df.at[idx, "Cuota local"] = m["Cuota local API"]
                df.at[idx, "Cuota empate"] = m["Cuota empate API"]
                df.at[idx, "Cuota visitante"] = m["Cuota visitante API"]

            df.at[idx, "Bookmaker"] = m["Bookmaker"]
            df.at[idx, "Bookmakers usados"] = m.get("Cantidad bookmakers", None)

    return df.drop(columns=["local_norm", "visitante_norm"], errors="ignore")


def calcular_probabilidades(cuota_local, cuota_empate, cuota_visitante):
    try:
        cl = float(cuota_local)
        ce = float(cuota_empate)
        cv = float(cuota_visitante)

        if cl <= 1 or ce <= 1 or cv <= 1:
            return None

        p_local = 1 / cl
        p_empate = 1 / ce
        p_visitante = 1 / cv
        margen = p_local + p_empate + p_visitante

        real_local = p_local / margen
        real_empate = p_empate / margen
        real_visitante = p_visitante / margen

        opciones = {
            "Local": real_local,
            "Empate": real_empate,
            "Visitante": real_visitante,
        }

        recomendacion = max(opciones, key=opciones.get)
        confianza = opciones[recomendacion]

        diff_1_2 = abs(real_local - real_visitante)

        if recomendacion == "Empate":
            resultado = "1-1"
        elif confianza >= 0.66:
            resultado = "3-0" if diff_1_2 >= 0.45 else "2-0"
        elif confianza >= 0.58:
            resultado = "2-0"
        elif confianza >= 0.50:
            resultado = "2-1"
        elif confianza >= 0.42:
            resultado = "1-0"
        else:
            resultado = "1-1"

        if confianza >= 0.58:
            riesgo = "Bajo"
        elif confianza >= 0.47:
            riesgo = "Medio"
        else:
            riesgo = "Alto"

        return {
            "Prob local %": round(real_local * 100, 2),
            "Prob empate %": round(real_empate * 100, 2),
            "Prob visitante %": round(real_visitante * 100, 2),
            "Margen casa %": round((margen - 1) * 100, 2),
            "Recomendación": recomendacion,
            "Confianza %": round(confianza * 100, 2),
            "Resultado probable": resultado,
            "Riesgo": riesgo,
        }
    except Exception:
        return None


def agregar_calculos(df):
    df = df.copy()

    columnas = [
        "Prob local %", "Prob empate %", "Prob visitante %",
        "Margen casa %", "Recomendación", "Confianza %",
        "Resultado probable", "Riesgo"
    ]

    for c in columnas:
        if c not in df.columns:
            df[c] = None

    for idx, row in df.iterrows():
        calc = calcular_probabilidades(row.get("Cuota local"), row.get("Cuota empate"), row.get("Cuota visitante"))
        if calc:
            for k, v in calc.items():
                df.at[idx, k] = v

    return df


def resultado_para_prode(row):
    rec = row.get("Recomendación")
    local = row.get("local", "Local")
    visitante = row.get("visitante", "Visitante")

    if rec == "Local":
        return f"Gana {local}"
    if rec == "Visitante":
        return f"Gana {visitante}"
    if rec == "Empate":
        return "Empate"
    return ""


def dataframe_to_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Recomendaciones")
    output.seek(0)
    return output.getvalue()


def filtro_texto(df, texto):
    if not texto:
        return df

    t = normalizar_nombre(texto)
    mask = (
        df["local"].astype(str).apply(normalizar_nombre).str.contains(t, na=False) |
        df["visitante"].astype(str).apply(normalizar_nombre).str.contains(t, na=False) |
        df.get("grupo", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(t, na=False) |
        df.get("ronda", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(t, na=False)
    )
    return df[mask]


st.title("⚽ Prode Mundial 2026")
st.caption("Fixture + cuotas The Odds API + probabilidades reales para armar un prode más fino.")

with st.sidebar:
    st.header("Estado")
    api_key = get_api_key()

    if api_key:
        st.success("API key detectada.")
    else:
        st.error("Falta ODDS_API_KEY en Secrets.")

    st.divider()
    st.header("Fuentes")
    st.link_button("Fixture OpenFootball", OPENFOOTBALL_URL)
    st.write("Cuotas: The Odds API")
    st.code(SPORT_KEY_MUNDIAL)

    st.divider()
    st.warning("Usá esto como ayuda para el prode, no como garantía. Las cuotas no son una bola de cristal, aunque vendan humo bastante profesional.")

if "fixture" not in st.session_state:
    st.session_state["fixture"] = pd.DataFrame()

tabs = st.tabs(["⚽ Partidos", "📈 Cuotas API", "🏆 Campeón", "⬇️ Exportar"])

with tabs[0]:
    st.header("1) Cargar cruces")

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("Cargar Mundial 2026", type="primary"):
            try:
                st.session_state["fixture"] = cargar_fixture_openfootball()
                st.success("Fixture cargado.")
            except Exception as e:
                st.error(f"No pude cargar el fixture: {e}")

    with col2:
        if st.button("Limpiar tabla"):
            st.session_state["fixture"] = pd.DataFrame()
            st.rerun()

    with col3:
        archivo = st.file_uploader("O subir CSV/Excel propio", type=["csv", "xlsx"])
        if archivo is not None:
            try:
                if archivo.name.endswith(".csv"):
                    st.session_state["fixture"] = pd.read_csv(archivo)
                else:
                    st.session_state["fixture"] = pd.read_excel(archivo)
                st.success("Archivo cargado.")
            except Exception as e:
                st.error(f"No pude leer el archivo: {e}")

    df = st.session_state["fixture"]

    if not df.empty:
        st.header("2) Ver / editar cuotas")

        colf1, colf2, colf3 = st.columns([1, 1, 2])
        with colf1:
            grupos = sorted([g for g in df.get("grupo", pd.Series()).dropna().unique() if str(g).strip()])
            grupo_sel = st.selectbox("Grupo", ["Todos"] + grupos) if grupos else "Todos"
        with colf2:
            rondas = sorted([r for r in df.get("ronda", pd.Series()).dropna().unique() if str(r).strip()])
            ronda_sel = st.selectbox("Ronda", ["Todas"] + rondas) if rondas else "Todas"
        with colf3:
            buscar = st.text_input("Buscar selección / ronda / grupo")

        mostrar = df.copy()
        if grupo_sel != "Todos":
            mostrar = mostrar[mostrar["grupo"] == grupo_sel]
        if ronda_sel != "Todas":
            mostrar = mostrar[mostrar["ronda"] == ronda_sel]
        mostrar = filtro_texto(mostrar, buscar)

        edited = st.data_editor(
            mostrar,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Cuota local": st.column_config.NumberColumn(format="%.2f"),
                "Cuota empate": st.column_config.NumberColumn(format="%.2f"),
                "Cuota visitante": st.column_config.NumberColumn(format="%.2f"),
            },
            key="editor_partidos",
        )

        if st.button("Recalcular tabla visible"):
            resultado_visible = agregar_calculos(edited)
            st.dataframe(resultado_visible, use_container_width=True)

        st.header("3) Recomendaciones actuales")
        resultado = agregar_calculos(df)
        resultado["Para prode"] = resultado.apply(resultado_para_prode, axis=1)

        cols = [
            "fecha", "hora", "ronda", "grupo", "local", "visitante", "sede",
            "Cuota local", "Cuota empate", "Cuota visitante",
            "Prob local %", "Prob empate %", "Prob visitante %",
            "Recomendación", "Para prode", "Confianza %",
            "Resultado probable", "Riesgo", "Bookmaker", "Bookmakers usados"
        ]
        cols = [c for c in cols if c in resultado.columns]

        st.dataframe(resultado[cols], use_container_width=True)

        st.subheader("Ranking de picks más confiables")
        ranking = resultado.dropna(subset=["Confianza %"]).sort_values("Confianza %", ascending=False)
        st.dataframe(ranking[cols].head(20), use_container_width=True)
    else:
        st.info("Primero cargá el fixture del Mundial o subí tu propio archivo.")

with tabs[1]:
    st.header("Actualizar cuotas desde The Odds API")

    api_key = get_api_key()

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        regions = st.multiselect(
            "Regiones",
            ["us", "uk", "eu", "au"],
            default=["us", "uk", "eu"],
            help="Mientras más regiones, más bookmakers puede consultar y más créditos puede gastar."
        )
    with col2:
        usar_promedio = st.checkbox("Promediar bookmakers", value=True)
    with col3:
        st.write("Sport key usado:")
        st.code(SPORT_KEY_MUNDIAL)

    if st.button("Actualizar cuotas del Mundial", type="primary"):
        if not api_key:
            st.error("Falta ODDS_API_KEY en Secrets.")
        elif st.session_state["fixture"].empty:
            st.warning("Primero cargá el fixture en la pestaña Partidos.")
        else:
            try:
                eventos = consultar_odds(api_key, SPORT_KEY_MUNDIAL, ",".join(regions), "h2h")
                df_odds = eventos_a_tabla_odds(eventos, usar_promedio=usar_promedio)

                if df_odds.empty:
                    st.warning("La API respondió, pero no encontré cuotas 1X2 disponibles para los partidos.")
                    st.json(eventos[:3] if isinstance(eventos, list) else eventos)
                else:
                    st.session_state["odds_raw"] = df_odds
                    conectado = conectar_fixture_con_odds(st.session_state["fixture"], df_odds)
                    st.session_state["fixture"] = agregar_calculos(conectado)
                    st.success("Cuotas conectadas con el fixture.")

                headers = st.session_state.get("odds_headers", {})
                if headers:
                    st.info(
                        f"Requests usadas: {headers.get('requests_used')} | "
                        f"Restantes: {headers.get('requests_remaining')} | "
                        f"Costo última consulta: {headers.get('requests_last')}"
                    )

            except Exception as e:
                st.error(str(e))

    if st.button("Ver deportes disponibles de mi API"):
        if not api_key:
            st.error("Falta ODDS_API_KEY en Secrets.")
        else:
            try:
                deportes = consultar_deportes(api_key)
                df_deportes = pd.DataFrame(deportes)
                st.dataframe(df_deportes, use_container_width=True)
            except Exception as e:
                st.error(str(e))

    if "odds_raw" in st.session_state:
        st.subheader("Cuotas crudas encontradas")
        st.dataframe(st.session_state["odds_raw"], use_container_width=True)

with tabs[2]:
    st.header("Cuotas de campeón del mundo")

    api_key = get_api_key()

    if st.button("Consultar ganador del Mundial"):
        if not api_key:
            st.error("Falta ODDS_API_KEY en Secrets.")
        else:
            try:
                eventos = consultar_odds(api_key, SPORT_KEY_CAMPEON, "us,uk,eu", "outrights")
                filas = []

                for ev in eventos:
                    for bk in ev.get("bookmakers", []):
                        for market in bk.get("markets", []):
                            if market.get("key") != "outrights":
                                continue
                            for out in market.get("outcomes", []):
                                filas.append({
                                    "Selección": out.get("name"),
                                    "Cuota campeón": out.get("price"),
                                    "Bookmaker": bk.get("title"),
                                })

                df_campeon = pd.DataFrame(filas)
                if df_campeon.empty:
                    st.warning("No encontré cuotas de campeón.")
                else:
                    resumen = (
                        df_campeon.groupby("Selección", as_index=False)
                        .agg({"Cuota campeón": "mean", "Bookmaker": "count"})
                        .rename(columns={"Bookmaker": "Bookmakers"})
                    )
                    resumen["Cuota campeón"] = resumen["Cuota campeón"].round(2)
                    resumen["Prob implícita %"] = (100 / resumen["Cuota campeón"]).round(2)
                    resumen = resumen.sort_values("Cuota campeón")
                    st.dataframe(resumen, use_container_width=True)

            except Exception as e:
                st.error(str(e))

with tabs[3]:
    st.header("Exportar recomendaciones")

    df = st.session_state["fixture"]

    if df.empty:
        st.info("Todavía no hay datos para exportar.")
    else:
        resultado = agregar_calculos(df)
        resultado["Para prode"] = resultado.apply(resultado_para_prode, axis=1)

        csv = resultado.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Descargar CSV",
            csv,
            "prode_mundial_2026_recomendaciones.csv",
            "text/csv"
        )

        excel_bytes = dataframe_to_excel_bytes(resultado)
        st.download_button(
            "Descargar Excel",
            excel_bytes,
            "prode_mundial_2026_recomendaciones.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.dataframe(resultado, use_container_width=True)
