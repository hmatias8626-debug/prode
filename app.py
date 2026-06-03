import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from datetime import date, timedelta

st.set_page_config(
    page_title="Prode Odds",
    page_icon="⚽",
    layout="wide"
)

CATEGORIAS_RAPIDAS = [
    {"label": "🌎 Mundial 2026", "key": "soccer_fifa_world_cup", "modo": "h2h"},
    {"label": "🏆 Campeón Mundial", "key": "soccer_fifa_world_cup_winner", "modo": "outrights"},
    {"label": "🏆 Libertadores", "key": "soccer_conmebol_copa_libertadores", "modo": "h2h"},
    {"label": "🏆 Sudamericana", "key": "soccer_conmebol_copa_sudamericana", "modo": "h2h"},
    {"label": "🇨🇱 Chile Primera", "key": "soccer_chile_campeonato", "modo": "h2h"},
    {"label": "🇧🇷 Brasil Serie B", "key": "soccer_brazil_serie_b", "modo": "h2h"},
    {"label": "🇪🇸 España Segunda", "key": "soccer_spain_segunda_division", "modo": "h2h"},
    {"label": "🇯🇵 Japón J League", "key": "soccer_japan_j_league", "modo": "h2h"},
]

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"


def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None


def get_odds_key():
    return get_secret("ODDS_API_KEY")


def get_api_football_key():
    return get_secret("API_FOOTBALL_KEY")


def odds_api_get(url, params, timeout=30):
    r = requests.get(url, params=params, timeout=timeout)
    st.session_state["odds_headers"] = {
        "requests_used": r.headers.get("x-requests-used"),
        "requests_remaining": r.headers.get("x-requests-remaining"),
        "requests_last": r.headers.get("x-requests-last"),
    }
    if r.status_code != 200:
        raise Exception(f"Error The Odds API {r.status_code}: {r.text}")
    return r.json()


def api_football_get(endpoint, params=None, timeout=30):
    key = get_api_football_key()
    if not key:
        raise Exception("Falta API_FOOTBALL_KEY en Secrets.")

    headers = {"x-apisports-key": key}
    url = f"{API_FOOTBALL_BASE}{endpoint}"
    r = requests.get(url, headers=headers, params=params or {}, timeout=timeout)

    st.session_state["api_football_headers"] = {
        "requests_limit": r.headers.get("x-ratelimit-requests-limit"),
        "requests_remaining": r.headers.get("x-ratelimit-requests-remaining"),
    }

    if r.status_code != 200:
        raise Exception(f"Error API-Football {r.status_code}: {r.text}")

    data = r.json()

    errors = data.get("errors")
    if errors:
        raise Exception(f"API-Football respondió con error: {errors}")

    return data


@st.cache_data(ttl=1800)
def cargar_deportes_odds(api_key):
    url = "https://api.the-odds-api.com/v4/sports/"
    return pd.DataFrame(odds_api_get(url, {"apiKey": api_key}, timeout=25))


@st.cache_data(ttl=3600)
def cargar_ligas_argentina_api_football():
    data = api_football_get("/leagues", {"country": "Argentina"}, timeout=30)
    filas = []

    for item in data.get("response", []):
        league = item.get("league", {})
        country = item.get("country", {})
        seasons = item.get("seasons", [])

        season_years = []
        for s in seasons:
            year = s.get("year")
            if year:
                season_years.append(year)

        filas.append({
            "league_id": league.get("id"),
            "league_name": league.get("name"),
            "league_type": league.get("type"),
            "country": country.get("name"),
            "seasons": sorted(season_years, reverse=True),
            "ultima_temporada": max(season_years) if season_years else None,
        })

    return pd.DataFrame(filas)


def encontrar_liga_profesional(df_ligas):
    if df_ligas.empty:
        return None

    nombres_prioridad = [
        "liga profesional argentina",
        "primera división",
        "primera division",
        "superliga",
        "liga profesional",
    ]

    tmp = df_ligas.copy()
    tmp["name_norm"] = tmp["league_name"].astype(str).str.lower()

    for nombre in nombres_prioridad:
        m = tmp[tmp["name_norm"].str.contains(nombre, na=False)]
        if not m.empty:
            return int(m.iloc[0]["league_id"])

    return int(tmp.iloc[0]["league_id"])


def cargar_fixtures_api_football(league_id, season, modo_fecha="next", cantidad=20, desde=None, hasta=None):
    params = {"league": int(league_id), "season": int(season)}

    if modo_fecha == "next":
        params["next"] = int(cantidad)
    elif modo_fecha == "rango":
        params["from"] = desde
        params["to"] = hasta
    elif modo_fecha == "last":
        params["last"] = int(cantidad)

    data = api_football_get("/fixtures", params=params, timeout=35)
    filas = []

    for item in data.get("response", []):
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        status = fixture.get("status", {}) or {}

        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}

        filas.append({
            "fecha_api": fixture.get("date"),
            "liga": league.get("name"),
            "temporada": league.get("season"),
            "ronda": league.get("round"),
            "local": home.get("name"),
            "visitante": away.get("name"),
            "estado": status.get("long"),
            "goles_local": goals.get("home"),
            "goles_visitante": goals.get("away"),
            "Cuota local": None,
            "Cuota empate": None,
            "Cuota visitante": None,
            "Bookmaker": "Manual/API-Football",
            "Bookmakers usados": None,
        })

    return pd.DataFrame(filas)


def consultar_eventos_odds(api_key, sport_key, regions, markets):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    return odds_api_get(url, params, timeout=35)


def promedio(lista):
    return round(sum(lista) / len(lista), 2) if lista else None


def eventos_h2h_a_df(eventos, promediar=True):
    filas = []

    for ev in eventos:
        local = ev.get("home_team", "")
        visitante = ev.get("away_team", "")
        fecha_iso = ev.get("commence_time", "")

        cuotas_local, cuotas_empate, cuotas_visitante, casas = [], [], [], []

        for bk in ev.get("bookmakers", []):
            for market in bk.get("markets", []):
                if market.get("key") != "h2h":
                    continue

                outcomes = market.get("outcomes", [])
                precios = {o.get("name", ""): o.get("price") for o in outcomes}

                cuota_local = precios.get(local)
                cuota_visitante = precios.get(visitante)
                cuota_empate = precios.get("Draw") or precios.get("Empate") or precios.get("draw")

                if cuota_local and cuota_visitante:
                    cuotas_local.append(float(cuota_local))
                    cuotas_visitante.append(float(cuota_visitante))
                    casas.append(bk.get("title", ""))

                    if cuota_empate:
                        cuotas_empate.append(float(cuota_empate))

                    if not promediar:
                        break

            if casas and not promediar:
                break

        if casas:
            filas.append({
                "fecha_api": fecha_iso,
                "local": local,
                "visitante": visitante,
                "Cuota local": promedio(cuotas_local),
                "Cuota empate": promedio(cuotas_empate),
                "Cuota visitante": promedio(cuotas_visitante),
                "Bookmaker": "Promedio" if promediar and len(casas) > 1 else casas[0],
                "Bookmakers usados": len(casas),
            })

    return pd.DataFrame(filas)


def eventos_outrights_a_df(eventos):
    filas = []

    for ev in eventos:
        torneo = ev.get("sport_title", "")
        fecha = ev.get("commence_time", "")

        for bk in ev.get("bookmakers", []):
            for market in bk.get("markets", []):
                if market.get("key") != "outrights":
                    continue

                for out in market.get("outcomes", []):
                    cuota = out.get("price")
                    if cuota:
                        filas.append({
                            "torneo": torneo,
                            "fecha_api": fecha,
                            "selección/equipo": out.get("name"),
                            "Cuota": float(cuota),
                            "Prob implícita %": round(100 / float(cuota), 2),
                            "Bookmaker": bk.get("title", ""),
                        })

    return pd.DataFrame(filas)


def calcular_probabilidades_partido(row):
    try:
        cl = float(row["Cuota local"])
        cv = float(row["Cuota visitante"])
        hay_empate = pd.notna(row.get("Cuota empate"))

        if hay_empate:
            ce = float(row["Cuota empate"])
            bruto_local = 1 / cl
            bruto_empate = 1 / ce
            bruto_visitante = 1 / cv
            total = bruto_local + bruto_empate + bruto_visitante
            p_local = bruto_local / total
            p_empate = bruto_empate / total
            p_visitante = bruto_visitante / total
            opciones = {"Local": p_local, "Empate": p_empate, "Visitante": p_visitante}
        else:
            bruto_local = 1 / cl
            bruto_visitante = 1 / cv
            total = bruto_local + bruto_visitante
            p_local = bruto_local / total
            p_empate = None
            p_visitante = bruto_visitante / total
            opciones = {"Local": p_local, "Visitante": p_visitante}

        recomendacion = max(opciones, key=opciones.get)
        confianza = opciones[recomendacion]

        if recomendacion == "Local":
            para_prode = f"Gana {row['local']}"
        elif recomendacion == "Visitante":
            para_prode = f"Gana {row['visitante']}"
        else:
            para_prode = "Empate"

        if hay_empate:
            if recomendacion == "Empate":
                resultado = "1-1"
            elif confianza >= 0.62:
                resultado = "2-0"
            elif confianza >= 0.52:
                resultado = "2-1"
            else:
                resultado = "1-0"
        else:
            resultado = ""

        riesgo = "Bajo" if confianza >= 0.58 else "Medio" if confianza >= 0.47 else "Alto"

        return pd.Series({
            "Prob local %": round(p_local * 100, 2),
            "Prob empate %": round(p_empate * 100, 2) if p_empate is not None else None,
            "Prob visitante %": round(p_visitante * 100, 2),
            "Margen casa %": round((total - 1) * 100, 2),
            "Recomendación": recomendacion,
            "Para prode": para_prode,
            "Confianza %": round(confianza * 100, 2),
            "Resultado probable": resultado,
            "Riesgo": riesgo,
        })
    except Exception:
        return pd.Series({
            "Prob local %": None,
            "Prob empate %": None,
            "Prob visitante %": None,
            "Margen casa %": None,
            "Recomendación": None,
            "Para prode": None,
            "Confianza %": None,
            "Resultado probable": None,
            "Riesgo": None,
        })


def agregar_calculos(df):
    if df.empty:
        return df

    # Elimina columnas calculadas previas para evitar duplicados si se recalcula.
    calculadas = [
        "Prob local %", "Prob empate %", "Prob visitante %",
        "Margen casa %", "Recomendación", "Para prode",
        "Confianza %", "Resultado probable", "Riesgo"
    ]
    df = df.drop(columns=[c for c in calculadas if c in df.columns], errors="ignore")

    calculos = df.apply(calcular_probabilidades_partido, axis=1)
    return pd.concat([df.reset_index(drop=True), calculos.reset_index(drop=True)], axis=1)


def preparar_outrights(df_out):
    if df_out.empty:
        return df_out

    resumen = (
        df_out.groupby("selección/equipo", as_index=False)
        .agg({"Cuota": "mean", "Bookmaker": "count"})
        .rename(columns={"Bookmaker": "Bookmakers usados"})
    )
    resumen["Cuota"] = resumen["Cuota"].round(2)
    resumen["Prob implícita %"] = (100 / resumen["Cuota"]).round(2)
    return resumen.sort_values("Cuota")


def excel_bytes(df_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, df in df_dict.items():
            df.to_excel(writer, index=False, sheet_name=sheet[:31])
    output.seek(0)
    return output.getvalue()


def cargar_csv_excel(archivo):
    if archivo.name.endswith(".csv"):
        return pd.read_csv(archivo)
    return pd.read_excel(archivo)


def asegurar_columnas_manual(df):
    df = df.copy()
    necesarias = ["fecha_api", "local", "visitante", "Cuota local", "Cuota empate", "Cuota visitante"]
    for col in necesarias:
        if col not in df.columns:
            df[col] = None
    return df


st.title("⚽ Prode Odds")
st.caption("Botoncitos rápidos + The Odds API + Liga Argentina real con API-Football.")

odds_key = get_odds_key()
api_football_key = get_api_football_key()

with st.sidebar:
    st.header("Estado")

    if odds_key:
        st.success("ODDS_API_KEY detectada.")
    else:
        st.error("Falta ODDS_API_KEY.")

    if api_football_key:
        st.success("API_FOOTBALL_KEY detectada.")
    else:
        st.warning("Falta API_FOOTBALL_KEY para Liga Argentina.")

    st.divider()
    st.header("Secrets necesarios")
    st.code('ODDS_API_KEY = "tu_key_the_odds_api"\nAPI_FOOTBALL_KEY = "tu_key_api_football"', language="toml")

    st.divider()
    st.warning("Las cuotas ayudan, pero no garantizan resultados. El oráculo cobra margen y encima se lava las manos.")

if "df_resultado" not in st.session_state:
    st.session_state["df_resultado"] = pd.DataFrame()

if "titulo_actual" not in st.session_state:
    st.session_state["titulo_actual"] = ""

if "modo_actual" not in st.session_state:
    st.session_state["modo_actual"] = "h2h"

if "sport_key" not in st.session_state:
    st.session_state["sport_key"] = "soccer_fifa_world_cup"

st.header("1) Elegir competencia")

st.subheader("Accesos rápidos")

cols = st.columns(4)
for i, cat in enumerate(CATEGORIAS_RAPIDAS):
    with cols[i % 4]:
        if st.button(cat["label"], use_container_width=True):
            st.session_state["sport_key"] = cat["key"]
            st.session_state["modo_actual"] = cat["modo"]
            st.session_state["titulo_actual"] = cat["label"]
            st.session_state["df_resultado"] = pd.DataFrame()

cols_arg = st.columns([1, 3])
with cols_arg[0]:
    if st.button("🇦🇷 Liga Argentina", use_container_width=True):
        st.session_state["sport_key"] = "api_football_argentina"
        st.session_state["modo_actual"] = "api_football_argentina"
        st.session_state["titulo_actual"] = "🇦🇷 Liga Argentina"
        st.session_state["df_resultado"] = pd.DataFrame()

with cols_arg[1]:
    st.caption("Liga Argentina usa API-Football para traer fixture real. Las cuotas se completan manualmente o con otra fuente si luego conseguimos una API de odds argentina.")

st.divider()

with st.expander("Selector avanzado de The Odds API"):
    if not odds_key:
        st.error("Falta ODDS_API_KEY para usar el selector avanzado.")
    else:
        if "df_deportes" not in st.session_state:
            try:
                url = "https://api.the-odds-api.com/v4/sports/"
                st.session_state["df_deportes"] = pd.DataFrame(odds_api_get(url, {"apiKey": odds_key}, timeout=25))
            except Exception as e:
                st.error(f"No pude cargar deportes: {e}")
                st.session_state["df_deportes"] = pd.DataFrame()

        df_deportes = st.session_state["df_deportes"].copy()

        if not df_deportes.empty:
            df_soccer = df_deportes[df_deportes["group"].astype(str).str.lower().eq("soccer")].copy()
            df_soccer = df_soccer.sort_values(["title", "key"])

            buscar = st.text_input("Buscar categoría avanzada", placeholder="mundial, libertadores, chile, brazil...")
            df_lista = df_soccer.copy()
            if buscar:
                b = buscar.lower().strip()
                df_lista = df_soccer[
                    df_soccer["key"].astype(str).str.lower().str.contains(b, na=False)
                    | df_soccer["title"].astype(str).str.lower().str.contains(b, na=False)
                    | df_soccer["description"].astype(str).str.lower().str.contains(b, na=False)
                ]

            opciones = {
                f"{row['title']} — {row['key']}": row["key"]
                for _, row in df_lista.iterrows()
            }

            if opciones:
                seleccion = st.selectbox("Categoría avanzada", list(opciones.keys()))
                if st.button("Usar categoría seleccionada"):
                    key = opciones[seleccion]
                    info = df_deportes[df_deportes["key"] == key].iloc[0].to_dict()
                    st.session_state["sport_key"] = key
                    st.session_state["titulo_actual"] = seleccion
                    st.session_state["modo_actual"] = "outrights" if info.get("has_outrights") and "winner" in key else "h2h"
                    st.session_state["df_resultado"] = pd.DataFrame()

            st.dataframe(df_soccer, use_container_width=True)

sport_key = st.session_state.get("sport_key", "soccer_fifa_world_cup")
modo_actual = st.session_state.get("modo_actual", "h2h")
titulo_actual = st.session_state.get("titulo_actual", "🌎 Mundial 2026")

st.header(f"2) Consultar: {titulo_actual}")

if modo_actual == "api_football_argentina":
    if not api_football_key:
        st.error("Para usar Liga Argentina cargá API_FOOTBALL_KEY en Streamlit Cloud → Settings → Secrets.")
    else:
        try:
            df_ligas_arg = cargar_ligas_argentina_api_football()
        except Exception as e:
            st.error(f"No pude cargar ligas argentinas desde API-Football: {e}")
            df_ligas_arg = pd.DataFrame()

        if not df_ligas_arg.empty:
            st.subheader("Liga / torneo")

            # Priorizamos Liga Profesional, pero podés elegir otra.
            liga_default = encontrar_liga_profesional(df_ligas_arg)
            opciones_ligas = {
                f"{row['league_name']} — ID {row['league_id']} — temporadas: {row['seasons'][:5]}": int(row["league_id"])
                for _, row in df_ligas_arg.iterrows()
            }

            labels = list(opciones_ligas.keys())
            default_idx = 0
            for i, label in enumerate(labels):
                if f"ID {liga_default}" in label:
                    default_idx = i
                    break

            liga_label = st.selectbox("Seleccionar liga argentina", labels, index=default_idx)
            league_id = opciones_ligas[liga_label]

            fila_liga = df_ligas_arg[df_ligas_arg["league_id"] == league_id].iloc[0]
            temporadas = fila_liga["seasons"] if isinstance(fila_liga["seasons"], list) else [date.today().year]
            temporada_default = date.today().year if date.today().year in temporadas else temporadas[0]

            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                season = st.selectbox("Temporada", temporadas, index=temporadas.index(temporada_default) if temporada_default in temporadas else 0)
            with col2:
                modo_fecha = st.selectbox("Qué cargar", ["next", "last", "rango"], format_func=lambda x: {"next": "Próximos partidos", "last": "Últimos partidos", "rango": "Rango de fechas"}[x])
            with col3:
                st.caption("API-Football trae fixture. Las cuotas quedan editables para que puedas cargarlas si no hay odds automáticas.")

            if modo_fecha in ["next", "last"]:
                cantidad = st.slider("Cantidad de partidos", min_value=5, max_value=50, value=20, step=5)
                desde = hasta = None
            else:
                colf1, colf2 = st.columns(2)
                with colf1:
                    desde_date = st.date_input("Desde", value=date.today())
                with colf2:
                    hasta_date = st.date_input("Hasta", value=date.today() + timedelta(days=14))
                desde = desde_date.isoformat()
                hasta = hasta_date.isoformat()
                cantidad = 20

            if st.button("Cargar partidos de Liga Argentina", type="primary"):
                try:
                    df_fix = cargar_fixtures_api_football(
                        league_id=league_id,
                        season=season,
                        modo_fecha=modo_fecha,
                        cantidad=cantidad,
                        desde=desde,
                        hasta=hasta,
                    )

                    if df_fix.empty:
                        st.warning("API-Football respondió, pero no devolvió partidos para esos filtros.")
                    else:
                        st.session_state["df_resultado"] = agregar_calculos(df_fix)
                        st.success(f"Partidos cargados: {len(df_fix)}")

                    headers = st.session_state.get("api_football_headers", {})
                    st.caption(f"API-Football límite: {headers.get('requests_limit')} | restantes: {headers.get('requests_remaining')}")

                except Exception as e:
                    st.error(str(e))

            with st.expander("Ver ligas argentinas detectadas por API-Football"):
                st.dataframe(df_ligas_arg, use_container_width=True)

else:
    if not odds_key:
        st.error("Falta ODDS_API_KEY para consultar The Odds API.")
    else:
        modo_label = "Partidos 1X2" if modo_actual == "h2h" else "Campeón / Outrights"
        st.info(f"Sport key: {sport_key} | Modo: {modo_label}")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            regions = st.multiselect("Regiones", ["us", "uk", "eu", "au"], default=["us", "uk", "eu"])
        with col2:
            promediar = st.checkbox("Promediar casas", value=True)
        with col3:
            if st.button("Limpiar resultado"):
                st.session_state["df_resultado"] = pd.DataFrame()
                st.rerun()

        if modo_actual == "h2h":
            if st.button("Actualizar partidos y cuotas", type="primary"):
                try:
                    eventos = consultar_eventos_odds(odds_key, sport_key, ",".join(regions), "h2h")
                    df_partidos = eventos_h2h_a_df(eventos, promediar=promediar)

                    if df_partidos.empty:
                        st.warning("La API respondió, pero no encontró partidos/cuotas h2h para esta categoría.")
                        with st.expander("Ver respuesta cruda"):
                            st.json(eventos[:3] if isinstance(eventos, list) else eventos)
                    else:
                        st.session_state["df_resultado"] = agregar_calculos(df_partidos)
                        st.success(f"Partidos cargados: {len(st.session_state['df_resultado'])}")

                    headers = st.session_state.get("odds_headers", {})
                    st.caption(
                        f"Requests usadas: {headers.get('requests_used')} | "
                        f"Restantes: {headers.get('requests_remaining')} | "
                        f"Costo última consulta: {headers.get('requests_last')}"
                    )
                except Exception as e:
                    st.error(str(e))

        else:
            if st.button("Actualizar cuotas de campeón / ganador", type="primary"):
                try:
                    eventos = consultar_eventos_odds(odds_key, sport_key, ",".join(regions), "outrights")
                    df_out = eventos_outrights_a_df(eventos)

                    if df_out.empty:
                        st.warning("La API respondió, pero no encontró cuotas outright para esta categoría.")
                        with st.expander("Ver respuesta cruda"):
                            st.json(eventos[:3] if isinstance(eventos, list) else eventos)
                    else:
                        st.session_state["df_outrights_raw"] = df_out
                        st.session_state["df_resultado"] = preparar_outrights(df_out)
                        st.success(f"Opciones cargadas: {len(st.session_state['df_resultado'])}")

                    headers = st.session_state.get("odds_headers", {})
                    st.caption(
                        f"Requests usadas: {headers.get('requests_used')} | "
                        f"Restantes: {headers.get('requests_remaining')} | "
                        f"Costo última consulta: {headers.get('requests_last')}"
                    )
                except Exception as e:
                    st.error(str(e))

st.header("3) Resultado")

df = st.session_state["df_resultado"]

if df.empty:
    st.info("Todavía no hay resultados. Elegí una competencia y tocá actualizar.")
else:
    if "local" in df.columns and "visitante" in df.columns:
        st.caption("Podés editar las cuotas en la tabla. Después tocá 'Recalcular probabilidades'.")

        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Cuota local": st.column_config.NumberColumn(format="%.2f"),
                "Cuota empate": st.column_config.NumberColumn(format="%.2f"),
                "Cuota visitante": st.column_config.NumberColumn(format="%.2f"),
            },
            key="editor_resultado",
        )

        if st.button("Recalcular probabilidades"):
            st.session_state["df_resultado"] = agregar_calculos(edited)
            st.success("Probabilidades recalculadas.")
            st.rerun()

        mostrar = st.session_state["df_resultado"].copy()

        colf1, colf2 = st.columns([1, 2])
        with colf1:
            riesgo = st.selectbox("Filtrar riesgo", ["Todos", "Bajo", "Medio", "Alto"])
        with colf2:
            texto = st.text_input("Buscar equipo")

        if riesgo != "Todos" and "Riesgo" in mostrar.columns:
            mostrar = mostrar[mostrar["Riesgo"] == riesgo]

        if texto:
            t = texto.lower().strip()
            mostrar = mostrar[
                mostrar["local"].astype(str).str.lower().str.contains(t, na=False)
                | mostrar["visitante"].astype(str).str.lower().str.contains(t, na=False)
            ]

        cols = [
            "fecha_api", "liga", "ronda", "local", "visitante", "estado",
            "goles_local", "goles_visitante",
            "Cuota local", "Cuota empate", "Cuota visitante",
            "Prob local %", "Prob empate %", "Prob visitante %",
            "Para prode", "Confianza %", "Resultado probable",
            "Riesgo", "Margen casa %", "Bookmaker", "Bookmakers usados"
        ]
        cols = [c for c in cols if c in mostrar.columns]

        st.dataframe(mostrar[cols], use_container_width=True)

        st.subheader("Top picks por confianza")
        ranking = mostrar.dropna(subset=["Confianza %"]).sort_values("Confianza %", ascending=False)
        st.dataframe(ranking[cols].head(20), use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)

st.header("4) Exportar")

if not df.empty:
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Descargar CSV", csv, "prode_odds_resultado.csv", "text/csv")

    hojas = {"Resultado": df}
    if "df_outrights_raw" in st.session_state and modo_actual == "outrights":
        hojas["Outrights_raw"] = st.session_state["df_outrights_raw"]

    st.download_button(
        "Descargar Excel",
        excel_bytes(hojas),
        "prode_odds_resultado.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
