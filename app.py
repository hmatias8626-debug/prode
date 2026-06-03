import streamlit as st
import pandas as pd
import requests
from io import BytesIO

st.set_page_config(
    page_title="Prode Odds - Multi Categoría",
    page_icon="⚽",
    layout="wide"
)

DEFAULT_SPORTS = [
    "soccer_fifa_world_cup",
    "soccer_conmebol_copa_libertadores",
    "soccer_conmebol_copa_sudamericana",
    "soccer_brazil_serie_b",
    "soccer_chile_campeonato",
    "soccer_spain_segunda_division",
    "soccer_japan_j_league",
    "soccer_fifa_world_cup_winner",
]


def get_api_key():
    try:
        return st.secrets["ODDS_API_KEY"]
    except Exception:
        return None


def api_get(url, params, timeout=30):
    r = requests.get(url, params=params, timeout=timeout)
    st.session_state["api_headers"] = {
        "requests_used": r.headers.get("x-requests-used"),
        "requests_remaining": r.headers.get("x-requests-remaining"),
        "requests_last": r.headers.get("x-requests-last"),
    }
    if r.status_code != 200:
        raise Exception(f"Error API {r.status_code}: {r.text}")
    return r.json()


@st.cache_data(ttl=1800)
def cargar_deportes(api_key):
    url = "https://api.the-odds-api.com/v4/sports/"
    data = api_get(url, {"apiKey": api_key}, timeout=25)
    return pd.DataFrame(data)


def consultar_eventos(api_key, sport_key, regions, markets):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    return api_get(url, params, timeout=35)


def promedio(lista):
    if not lista:
        return None
    return round(sum(lista) / len(lista), 2)


def eventos_h2h_a_df(eventos, promediar=True):
    filas = []

    for ev in eventos:
        local = ev.get("home_team", "")
        visitante = ev.get("away_team", "")
        fecha_iso = ev.get("commence_time", "")

        cuotas_local = []
        cuotas_empate = []
        cuotas_visitante = []
        casas = []

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

                    # En fútbol debería existir empate. En otros deportes puede no existir.
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

            opciones = {
                "Local": p_local,
                "Empate": p_empate,
                "Visitante": p_visitante,
            }

            margen = (total - 1) * 100
        else:
            bruto_local = 1 / cl
            bruto_visitante = 1 / cv
            total = bruto_local + bruto_visitante

            p_local = bruto_local / total
            p_empate = None
            p_visitante = bruto_visitante / total

            opciones = {
                "Local": p_local,
                "Visitante": p_visitante,
            }

            margen = (total - 1) * 100

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

        if confianza >= 0.58:
            riesgo = "Bajo"
        elif confianza >= 0.47:
            riesgo = "Medio"
        else:
            riesgo = "Alto"

        return pd.Series({
            "Prob local %": round(p_local * 100, 2),
            "Prob empate %": round(p_empate * 100, 2) if p_empate is not None else None,
            "Prob visitante %": round(p_visitante * 100, 2),
            "Margen casa %": round(margen, 2),
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

    calculos = df.apply(calcular_probabilidades_partido, axis=1)
    return pd.concat([df.reset_index(drop=True), calculos.reset_index(drop=True)], axis=1)


def excel_bytes(df_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, df in df_dict.items():
            safe = sheet[:31]
            df.to_excel(writer, index=False, sheet_name=safe)
    output.seek(0)
    return output.getvalue()


st.title("⚽ Prode Odds - Multi Categoría")
st.caption("Elegí torneo/categoría, traé cuotas desde The Odds API y armá recomendaciones para el prode.")

api_key = get_api_key()

with st.sidebar:
    st.header("Estado")
    if api_key:
        st.success("API key detectada.")
    else:
        st.error("Falta ODDS_API_KEY en Secrets.")

    st.divider()
    st.header("Modo")
    modo = st.radio(
        "Qué querés ver",
        ["Partidos 1X2 / Ganador", "Campeón / Outrights"],
        index=0
    )

    st.divider()
    st.warning("Esto ayuda a decidir, pero no garantiza resultados. Las cuotas son mercado + margen de la casa.")

if not api_key:
    st.stop()

if "df_resultado" not in st.session_state:
    st.session_state["df_resultado"] = pd.DataFrame()

if "df_deportes" not in st.session_state:
    try:
        st.session_state["df_deportes"] = cargar_deportes(api_key)
    except Exception as e:
        st.error(f"No pude cargar deportes: {e}")
        st.stop()

df_deportes = st.session_state["df_deportes"].copy()

st.header("1) Seleccionar categoría")

df_soccer = df_deportes[df_deportes["group"].astype(str).str.lower().eq("soccer")].copy()
df_soccer = df_soccer.sort_values(["title", "key"])

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    solo_favoritos = st.checkbox("Mostrar solo categorías principales", value=True)

with col2:
    buscar = st.text_input("Buscar categoría", placeholder="mundial, libertadores, sudamericana, chile, brazil...")

with col3:
    st.metric("Categorías Soccer", len(df_soccer))

df_lista = df_soccer.copy()

if solo_favoritos:
    df_lista = df_lista[df_lista["key"].isin(DEFAULT_SPORTS)]

if buscar:
    b = buscar.lower().strip()
    df_lista = df_soccer[
        df_soccer["key"].astype(str).str.lower().str.contains(b, na=False)
        | df_soccer["title"].astype(str).str.lower().str.contains(b, na=False)
        | df_soccer["description"].astype(str).str.lower().str.contains(b, na=False)
    ]

if df_lista.empty:
    st.warning("No encontré categorías con ese filtro.")
    st.dataframe(df_soccer, use_container_width=True)
    st.stop()

opciones = {
    f"{row['title']} — {row['key']}": row["key"]
    for _, row in df_lista.iterrows()
}

seleccion = st.selectbox("Categoría", list(opciones.keys()))
sport_key = opciones[seleccion]

info_categoria = df_deportes[df_deportes["key"] == sport_key].iloc[0].to_dict()

col_info1, col_info2, col_info3 = st.columns(3)
col_info1.info(f"Key: {sport_key}")
col_info2.info(f"Activa: {info_categoria.get('active')}")
col_info3.info(f"Outrights: {info_categoria.get('has_outrights')}")

st.header("2) Consultar cuotas")

if modo == "Partidos 1X2 / Ganador":
    col_a, col_b, col_c = st.columns([2, 1, 1])

    with col_a:
        regions = st.multiselect(
            "Regiones",
            ["us", "uk", "eu", "au"],
            default=["us", "uk", "eu"]
        )

    with col_b:
        promediar = st.checkbox("Promediar casas", value=True)

    with col_c:
        st.write("Mercado")
        st.code("h2h")

    if st.button("Actualizar partidos y cuotas", type="primary"):
        try:
            eventos = consultar_eventos(api_key, sport_key, ",".join(regions), "h2h")
            df_partidos = eventos_h2h_a_df(eventos, promediar=promediar)

            if df_partidos.empty:
                st.warning("La API respondió, pero no encontró partidos/cuotas h2h para esta categoría.")
                with st.expander("Ver respuesta cruda"):
                    st.json(eventos[:3] if isinstance(eventos, list) else eventos)
            else:
                st.session_state["df_resultado"] = agregar_calculos(df_partidos)
                st.success(f"Partidos cargados: {len(st.session_state['df_resultado'])}")

            headers = st.session_state.get("api_headers", {})
            st.caption(
                f"Requests usadas: {headers.get('requests_used')} | "
                f"Restantes: {headers.get('requests_remaining')} | "
                f"Costo última consulta: {headers.get('requests_last')}"
            )

        except Exception as e:
            st.error(str(e))

else:
    if not info_categoria.get("has_outrights"):
        st.warning("Esta categoría no figura con mercado outright. Probablemente no tenga cuotas de campeón.")

    if st.button("Actualizar cuotas de campeón / ganador", type="primary"):
        try:
            eventos = consultar_eventos(api_key, sport_key, "us,uk,eu", "outrights")
            df_out = eventos_outrights_a_df(eventos)

            if df_out.empty:
                st.warning("La API respondió, pero no encontró cuotas outright para esta categoría.")
                with st.expander("Ver respuesta cruda"):
                    st.json(eventos[:3] if isinstance(eventos, list) else eventos)
            else:
                resumen = (
                    df_out.groupby("selección/equipo", as_index=False)
                    .agg({
                        "Cuota": "mean",
                        "Bookmaker": "count"
                    })
                    .rename(columns={"Bookmaker": "Bookmakers usados"})
                )
                resumen["Cuota"] = resumen["Cuota"].round(2)
                resumen["Prob implícita %"] = (100 / resumen["Cuota"]).round(2)
                resumen = resumen.sort_values("Cuota")

                st.session_state["df_resultado"] = resumen
                st.session_state["df_outrights_raw"] = df_out
                st.success(f"Opciones cargadas: {len(resumen)}")

            headers = st.session_state.get("api_headers", {})
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
    st.info("Todavía no hay resultados. Elegí una categoría y tocá actualizar.")
else:
    if modo == "Partidos 1X2 / Ganador":
        colf1, colf2 = st.columns([1, 2])
        with colf1:
            riesgo = st.selectbox("Filtrar riesgo", ["Todos", "Bajo", "Medio", "Alto"])
        with colf2:
            texto = st.text_input("Buscar equipo")

        mostrar = df.copy()

        if riesgo != "Todos" and "Riesgo" in mostrar.columns:
            mostrar = mostrar[mostrar["Riesgo"] == riesgo]

        if texto:
            t = texto.lower().strip()
            mostrar = mostrar[
                mostrar["local"].astype(str).str.lower().str.contains(t, na=False)
                | mostrar["visitante"].astype(str).str.lower().str.contains(t, na=False)
            ]

        cols = [
            "fecha_api", "local", "visitante",
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
        if "df_outrights_raw" in st.session_state:
            with st.expander("Ver cuotas crudas por bookmaker"):
                st.dataframe(st.session_state["df_outrights_raw"], use_container_width=True)

st.header("4) Exportar")

if not df.empty:
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Descargar CSV",
        csv,
        "prode_odds_resultado.csv",
        "text/csv"
    )

    hojas = {"Resultado": df}
    if "df_outrights_raw" in st.session_state and modo == "Campeón / Outrights":
        hojas["Outrights_raw"] = st.session_state["df_outrights_raw"]

    xlsx = excel_bytes(hojas)
    st.download_button(
        "Descargar Excel",
        xlsx,
        "prode_odds_resultado.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

with st.expander("Ver todas las categorías disponibles"):
    st.dataframe(df_deportes, use_container_width=True)
