import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from datetime import date, timedelta, datetime, timezone

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

CACHE_TABLE = "api_cache"
CACHE_TTL_HOURS = {
    "sports_list": 168,
    "api_football_leagues": 168,
    "api_football_fixtures": 24,
    "odds_h2h": 6,
    "odds_outrights": 12,
    "odds_api_io": 6,
}
FREE_API_FOOTBALL_SEASONS = [2024, 2023, 2022]


def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None


def get_odds_key():
    return get_secret("ODDS_API_KEY")


def get_api_football_key():
    return get_secret("API_FOOTBALL_KEY")


def get_odds_api_io_key():
    return get_secret("ODDS_API_IO_KEY")


def get_odds_api_io_base_url():
    return get_secret("ODDS_API_IO_BASE_URL") or "https://api.odds-api.io"


def get_supabase_url():
    return get_secret("SUPABASE_URL")


def get_supabase_key():
    return get_secret("SUPABASE_SERVICE_KEY") or get_secret("SUPABASE_ANON_KEY")



def supabase_enabled():
    return bool(get_supabase_url() and get_supabase_key())


def supabase_headers():
    key = get_supabase_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_iso_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def cache_age_hours(created_at):
    dt = parse_iso_dt(created_at)
    if not dt:
        return 999999
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def supabase_get_cache(cache_key, ttl_hours=None):
    if not supabase_enabled():
        return None, "Supabase no configurado"

    url = f"{get_supabase_url().rstrip('/')}/rest/v1/{CACHE_TABLE}"
    params = {
        "cache_key": f"eq.{cache_key}",
        "select": "cache_key,payload,created_at",
        "limit": "1",
    }

    r = requests.get(url, headers=supabase_headers(), params=params, timeout=20)

    if r.status_code != 200:
        return None, f"Error leyendo cache Supabase {r.status_code}: {r.text[:500]}"

    rows = r.json()
    if not rows:
        return None, "No hay cache guardado"

    row = rows[0]
    age = cache_age_hours(row.get("created_at"))

    if ttl_hours is not None and age > ttl_hours:
        return None, f"Cache vencido: {age:.1f} h"

    return row.get("payload"), f"Cache OK: {age:.1f} h"


def supabase_set_cache(cache_key, payload):
    if not supabase_enabled():
        return False, "Supabase no configurado"

    url = f"{get_supabase_url().rstrip('/')}/rest/v1/{CACHE_TABLE}"
    data = {
        "cache_key": cache_key,
        "payload": payload,
        "created_at": utc_now_iso(),
    }

    r = requests.post(url, headers=supabase_headers(), json=data, timeout=20)

    if r.status_code not in [200, 201, 204]:
        return False, f"Error guardando cache Supabase {r.status_code}: {r.text[:500]}"

    return True, "Cache guardado"


def cache_key_odds(sport_key, regions, markets):
    safe_regions = str(regions).replace(",", "_")
    return f"odds::{sport_key}::{markets}::{safe_regions}"


def cache_key_api_football_fixtures(league_id, season, modo_fecha, cantidad, desde, hasta):
    return f"api_football_fixtures::{league_id}::{season}::{modo_fecha}::{cantidad}::{desde}::{hasta}"


def get_or_fetch_cache(cache_key, ttl_hours, fetch_fn, force=False):
    if not force:
        cached, msg = supabase_get_cache(cache_key, ttl_hours=ttl_hours)
        if cached is not None:
            st.session_state["cache_status"] = f"Usando Supabase: {msg}"
            return cached, "cache"

    data = fetch_fn()
    ok, msg = supabase_set_cache(cache_key, data)
    st.session_state["cache_status"] = f"API consultada. {msg}"
    return data, "api"



def odds_api_io_get(endpoint, params=None, timeout=30):
    """
    odds-api.io no expone una documentación pública fácil de encontrar desde acá.
    Por eso dejamos el endpoint configurable por Secret y probamos rutas comunes.
    Secrets opcionales:
    ODDS_API_IO_BASE_URL = "https://api.odds-api.io"
    """
    key = get_odds_api_io_key()
    if not key:
        raise Exception("Falta ODDS_API_IO_KEY en Secrets.")

    base = get_odds_api_io_base_url().rstrip("/")
    url = endpoint if str(endpoint).startswith("http") else f"{base}/{str(endpoint).lstrip('/')}"

    params = dict(params or {})
    # Mandamos la key de varias formas comunes; si la API usa una sola, ignora el resto.
    params.setdefault("apiKey", key)
    params.setdefault("api_key", key)

    headers = {
        "Authorization": f"Bearer {key}",
        "X-API-Key": key,
        "x-api-key": key,
    }

    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    st.session_state["odds_api_io_last_url"] = r.url
    st.session_state["odds_api_io_status"] = r.status_code

    if r.status_code != 200:
        raise Exception(f"Error Odds-API.io {r.status_code}: {r.text[:800]}")

    try:
        return r.json()
    except Exception:
        raise Exception(f"Odds-API.io no devolvió JSON. Respuesta: {r.text[:800]}")


def odds_api_io_try_common_endpoints(force_api=False):
    """
    Prueba varias rutas comunes para descubrir cuál responde con la key.
    Si el dashboard de odds-api.io te da un endpoint exacto, conviene ponerlo en:
    ODDS_API_IO_EVENTS_ENDPOINT = "/..."
    """
    custom = get_secret("ODDS_API_IO_EVENTS_ENDPOINT")
    candidates = []

    if custom:
        candidates.append((custom, {"sport": "soccer", "league": "argentina", "country": "Argentina"}))

    candidates += [
        ("/v1/odds", {"sport": "soccer", "league": "argentina"}),
        ("/v2/odds", {"sport": "soccer", "league": "argentina"}),
        ("/v3/odds", {"sport": "soccer", "league": "argentina"}),
        ("/odds", {"sport": "soccer", "league": "argentina"}),
        ("/events", {"sport": "soccer", "league": "argentina"}),
        ("/v1/events", {"sport": "soccer", "league": "argentina"}),
        ("/v2/events", {"sport": "soccer", "league": "argentina"}),
        ("/sports", {}),
        ("/v1/sports", {}),
        ("/v2/sports", {}),
    ]

    cache_key = "odds_api_io::argentina::discovery"

    if not force_api:
        cached, msg = supabase_get_cache(cache_key, ttl_hours=CACHE_TTL_HOURS["odds_api_io"])
        if cached is not None:
            st.session_state["cache_status"] = f"Usando Supabase: {msg}"
            return cached.get("endpoint"), cached.get("data"), cached.get("errores", [])

    errores = []
    for endpoint, params in candidates:
        try:
            data = odds_api_io_get(endpoint, params=params)
            supabase_set_cache(cache_key, {"endpoint": endpoint, "data": data, "errores": errores})
            st.session_state["cache_status"] = "API Odds-API.io consultada y guardada en Supabase"
            return endpoint, data, errores
        except Exception as e:
            errores.append({"endpoint": endpoint, "error": str(e)[:500]})

    supabase_set_cache(cache_key, {"endpoint": None, "data": None, "errores": errores})
    return None, None, errores


def extraer_lista_eventos_odds_api_io(data):
    """
    Parser flexible para respuestas típicas:
    - lista directa
    - {"data": [...]}
    - {"events": [...]}
    - {"response": [...]}
    - {"results": [...]}
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["data", "events", "response", "results", "odds"]:
            val = data.get(key)
            if isinstance(val, list):
                return val

        # A veces viene {"data": {"events": [...]}}
        for val in data.values():
            if isinstance(val, dict):
                nested = extraer_lista_eventos_odds_api_io(val)
                if nested:
                    return nested

    return []


def normalizar_texto_equipo(x):
    import unicodedata
    if x is None:
        return ""
    s = str(x).lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace(".", "").replace("-", " ")
    return " ".join(s.split())


def parsear_eventos_odds_api_io_a_h2h(data):
    """
    Intenta convertir respuesta de odds-api.io a columnas:
    fecha_api, local, visitante, cuotas.
    Soporta estructuras similares a The Odds API y algunas variantes comunes.
    """
    eventos = extraer_lista_eventos_odds_api_io(data)
    filas = []

    for ev in eventos:
        if not isinstance(ev, dict):
            continue

        local = (
            ev.get("home_team") or ev.get("homeTeam") or ev.get("home") or
            ev.get("team_home") or ev.get("local") or ev.get("home_name")
        )
        visitante = (
            ev.get("away_team") or ev.get("awayTeam") or ev.get("away") or
            ev.get("team_away") or ev.get("visitor") or ev.get("visitante") or ev.get("away_name")
        )
        fecha = ev.get("commence_time") or ev.get("start_time") or ev.get("date") or ev.get("time")

        cuota_local = ev.get("home_odds") or ev.get("home_price") or ev.get("odds_home")
        cuota_empate = ev.get("draw_odds") or ev.get("draw_price") or ev.get("odds_draw")
        cuota_visitante = ev.get("away_odds") or ev.get("away_price") or ev.get("odds_away")

        # Formato tipo The Odds API
        bookmakers = ev.get("bookmakers") or ev.get("books") or []
        cuotas_l, cuotas_e, cuotas_v, casas = [], [], [], []

        if isinstance(bookmakers, list):
            for bk in bookmakers:
                if not isinstance(bk, dict):
                    continue
                casa = bk.get("title") or bk.get("name") or bk.get("bookmaker") or "Odds-API.io"
                markets = bk.get("markets") or bk.get("odds") or []
                if isinstance(markets, dict):
                    markets = [markets]

                for market in markets:
                    if not isinstance(market, dict):
                        continue
                    key = str(market.get("key") or market.get("market") or market.get("name") or "").lower()
                    if key and key not in ["h2h", "match winner", "1x2", "winner", "moneyline"]:
                        continue

                    outcomes = market.get("outcomes") or market.get("prices") or []
                    if isinstance(outcomes, dict):
                        outcomes = [{"name": k, "price": v} for k, v in outcomes.items()]

                    precios = {}
                    for o in outcomes:
                        if not isinstance(o, dict):
                            continue
                        name = o.get("name") or o.get("label") or o.get("team")
                        price = o.get("price") or o.get("odds") or o.get("value")
                        precios[normalizar_texto_equipo(name)] = price

                    nl = normalizar_texto_equipo(local)
                    nv = normalizar_texto_equipo(visitante)
                    ch = precios.get(nl)
                    ca = precios.get(nv)
                    cd = precios.get("draw") or precios.get("empate") or precios.get("x")

                    if ch and ca:
                        cuotas_l.append(float(ch))
                        cuotas_v.append(float(ca))
                        if cd:
                            cuotas_e.append(float(cd))
                        casas.append(casa)

        if cuotas_l:
            cuota_local = round(sum(cuotas_l) / len(cuotas_l), 2)
            cuota_visitante = round(sum(cuotas_v) / len(cuotas_v), 2)
            cuota_empate = round(sum(cuotas_e) / len(cuotas_e), 2) if cuotas_e else None
            bookmaker = "Promedio Odds-API.io" if len(casas) > 1 else casas[0]
            usados = len(casas)
        else:
            bookmaker = "Odds-API.io"
            usados = 1 if cuota_local and cuota_visitante else None

        if local and visitante and cuota_local and cuota_visitante:
            filas.append({
                "fecha_api": fecha,
                "local": local,
                "visitante": visitante,
                "Cuota local": float(cuota_local),
                "Cuota empate": float(cuota_empate) if cuota_empate else None,
                "Cuota visitante": float(cuota_visitante),
                "Bookmaker": bookmaker,
                "Bookmakers usados": usados,
            })

    return pd.DataFrame(filas)


def intentar_cruzar_cuotas_argentina_con_odds_api_io(df_fixture, df_odds):
    if df_fixture.empty or df_odds.empty:
        return df_fixture

    df = df_fixture.copy()
    odds = df_odds.copy()

    df["local_norm"] = df["local"].apply(normalizar_texto_equipo)
    df["visitante_norm"] = df["visitante"].apply(normalizar_texto_equipo)
    odds["local_norm"] = odds["local"].apply(normalizar_texto_equipo)
    odds["visitante_norm"] = odds["visitante"].apply(normalizar_texto_equipo)

    for idx, row in df.iterrows():
        local = row["local_norm"]
        visitante = row["visitante_norm"]

        m = odds[(odds["local_norm"] == local) & (odds["visitante_norm"] == visitante)]
        invertido = False

        if m.empty:
            m = odds[(odds["local_norm"] == visitante) & (odds["visitante_norm"] == local)]
            invertido = not m.empty

        if not m.empty:
            x = m.iloc[0]
            if invertido:
                df.at[idx, "Cuota local"] = x["Cuota visitante"]
                df.at[idx, "Cuota empate"] = x.get("Cuota empate")
                df.at[idx, "Cuota visitante"] = x["Cuota local"]
            else:
                df.at[idx, "Cuota local"] = x["Cuota local"]
                df.at[idx, "Cuota empate"] = x.get("Cuota empate")
                df.at[idx, "Cuota visitante"] = x["Cuota visitante"]

            df.at[idx, "Bookmaker"] = x.get("Bookmaker", "Odds-API.io")
            df.at[idx, "Bookmakers usados"] = x.get("Bookmakers usados")

    return df.drop(columns=["local_norm", "visitante_norm"], errors="ignore")


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
    key = "sports_list::the_odds_api"

    def fetch():
        return odds_api_get(url, {"apiKey": api_key}, timeout=25)

    data, source = get_or_fetch_cache(key, CACHE_TTL_HOURS["sports_list"], fetch_fn=fetch, force=False)
    return pd.DataFrame(data)


@st.cache_data(ttl=3600)
def cargar_ligas_argentina_api_football():
    key = "api_football_leagues::Argentina"

    def fetch():
        return api_football_get("/leagues", {"country": "Argentina"}, timeout=30)

    data, source = get_or_fetch_cache(key, CACHE_TTL_HOURS["api_football_leagues"], fetch_fn=fetch, force=False)
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

        temporadas_free = [y for y in sorted(season_years, reverse=True) if y in FREE_API_FOOTBALL_SEASONS]

        filas.append({
            "league_id": league.get("id"),
            "league_name": league.get("name"),
            "league_type": league.get("type"),
            "country": country.get("name"),
            "seasons": sorted(season_years, reverse=True),
            "temporadas_free": temporadas_free,
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


def cargar_fixtures_api_football(league_id, season, modo_fecha="next", cantidad=20, desde=None, hasta=None, force_api=False):
    params = {"league": int(league_id), "season": int(season)}

    if modo_fecha == "next":
        params["next"] = int(cantidad)
    elif modo_fecha == "rango":
        params["from"] = desde
        params["to"] = hasta
    elif modo_fecha == "last":
        params["last"] = int(cantidad)

    key = cache_key_api_football_fixtures(league_id, season, modo_fecha, cantidad, desde, hasta)

    def fetch():
        return api_football_get("/fixtures", params=params, timeout=35)

    data, source = get_or_fetch_cache(key, CACHE_TTL_HOURS["api_football_fixtures"], fetch_fn=fetch, force=force_api)
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


def consultar_eventos_odds(api_key, sport_key, regions, markets, force_api=False):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }

    key = cache_key_odds(sport_key, regions, markets)
    ttl = CACHE_TTL_HOURS["odds_outrights"] if markets == "outrights" else CACHE_TTL_HOURS["odds_h2h"]

    def fetch():
        return odds_api_get(url, params, timeout=35)

    data, source = get_or_fetch_cache(key, ttl, fetch_fn=fetch, force=force_api)
    return data


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


def elegir_resultado_probable(p_local, p_empate, p_visitante):
    """
    Heurística simple para prode.
    No pretende simular xG real, pero evita tirar siempre 2-1.
    """
    if p_empate is not None and p_empate >= 0.34:
        if p_empate >= 0.40:
            return "0-0"
        if abs(p_local - p_visitante) <= 0.08:
            return "1-1"
        return "1-1"

    favorito = max(p_local, p_visitante)
    diferencia = abs(p_local - p_visitante)

    if favorito >= 0.72:
        return "3-0" if diferencia >= 0.55 else "3-1"

    if favorito >= 0.64:
        return "2-0" if diferencia >= 0.35 else "2-1"

    if favorito >= 0.56:
        return "2-1"

    if p_empate is not None and p_empate >= 0.29:
        return "1-1"

    if diferencia <= 0.10:
        return "1-1" if p_empate is not None else "1-0"

    return "1-0"


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

            # Para prode conviene permitir empate aunque no sea máximo absoluto si está muy cerca.
            max_no_empate = max(p_local, p_visitante)
            if p_empate >= 0.32 and (max_no_empate - p_empate) <= 0.06:
                recomendacion = "Empate"
            else:
                recomendacion = max(opciones, key=opciones.get)

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

        resultado = elegir_resultado_probable(p_local, p_empate, p_visitante)

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



def odds_api_io_events(league_slug="", limit=20, force_api=False):
    cache_key = f"odds_api_io_events::football::{league_slug}::{limit}"

    def fetch():
        params = {
            "apiKey": get_odds_api_io_key(),
            "sport": "football",
            "limit": int(limit),
        }
        if league_slug:
            params["league"] = league_slug
        return odds_api_io_get("/events", params=params, timeout=30)

    data, source = get_or_fetch_cache(
        cache_key,
        CACHE_TTL_HOURS["odds_api_io"],
        fetch_fn=fetch,
        force=force_api
    )
    return data


def odds_api_io_event_odds(event_id, bookmakers, force_api=False):
    cache_key = f"odds_api_io_odds::{event_id}::{bookmakers}"

    def fetch():
        params = {
            "apiKey": get_odds_api_io_key(),
            "eventId": event_id,
            "bookmakers": bookmakers,
        }
        return odds_api_io_get("/odds", params=params, timeout=30)

    data, source = get_or_fetch_cache(
        cache_key,
        CACHE_TTL_HOURS["odds_api_io"],
        fetch_fn=fetch,
        force=force_api
    )
    return data


def parse_odds_api_io_events(data):
    eventos = extraer_lista_eventos_odds_api_io(data)
    filas = []
    for ev in eventos:
        if not isinstance(ev, dict):
            continue
        sport = ev.get("sport") or {}
        league = ev.get("league") or {}
        filas.append({
            "event_id": ev.get("id"),
            "sport": sport.get("name") if isinstance(sport, dict) else sport,
            "sport_slug": sport.get("slug") if isinstance(sport, dict) else None,
            "league": league.get("name") if isinstance(league, dict) else league,
            "league_slug": league.get("slug") if isinstance(league, dict) else None,
            "fecha_api": ev.get("date"),
            "local": ev.get("home"),
            "visitante": ev.get("away"),
            "estado": ev.get("status"),
        })
    return pd.DataFrame(filas)


def parse_odds_api_io_odds_response(data):
    if not isinstance(data, dict):
        return None

    local = data.get("home")
    visitante = data.get("away")
    fecha = data.get("date")
    event_id = data.get("id")

    bookmakers = data.get("bookmakers") or {}
    cuotas_local, cuotas_empate, cuotas_visitante, casas = [], [], [], []

    if isinstance(bookmakers, dict):
        iterable = bookmakers.items()
    else:
        iterable = []

    for casa, markets in iterable:
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            name = str(market.get("name", "")).upper()
            if name not in ["ML", "1X2", "MATCH WINNER", "MONEYLINE"]:
                continue
            odds_list = market.get("odds") or []
            if not odds_list:
                continue
            odds = odds_list[0]
            try:
                home = odds.get("home")
                draw = odds.get("draw")
                away = odds.get("away")
                if home is not None and away is not None:
                    cuotas_local.append(float(home))
                    cuotas_visitante.append(float(away))
                    if draw is not None:
                        cuotas_empate.append(float(draw))
                    casas.append(casa)
            except Exception:
                pass

    if not cuotas_local:
        return None

    return {
        "event_id": event_id,
        "fecha_api": fecha,
        "local": local,
        "visitante": visitante,
        "Cuota local": round(sum(cuotas_local) / len(cuotas_local), 2),
        "Cuota empate": round(sum(cuotas_empate) / len(cuotas_empate), 2) if cuotas_empate else None,
        "Cuota visitante": round(sum(cuotas_visitante) / len(cuotas_visitante), 2),
        "Bookmaker": "Promedio Odds-API.io" if len(casas) > 1 else casas[0],
        "Bookmakers usados": len(casas),
    }


def cargar_cuotas_odds_api_io_por_eventos(league_slug="", limit=20, bookmakers="Bet365,Unibet,SingBet", force_api=False):
    eventos_raw = odds_api_io_events(league_slug=league_slug, limit=limit, force_api=force_api)
    df_eventos = parse_odds_api_io_events(eventos_raw)

    if df_eventos.empty:
        return pd.DataFrame(), df_eventos, eventos_raw

    filas = []
    for _, ev in df_eventos.iterrows():
        event_id = ev.get("event_id")
        if not event_id:
            continue
        try:
            raw_odds = odds_api_io_event_odds(event_id, bookmakers, force_api=force_api)
            parsed = parse_odds_api_io_odds_response(raw_odds)
            if parsed:
                parsed["local"] = parsed.get("local") or ev.get("local")
                parsed["visitante"] = parsed.get("visitante") or ev.get("visitante")
                parsed["fecha_api"] = parsed.get("fecha_api") or ev.get("fecha_api")
                parsed["league"] = ev.get("league")
                parsed["league_slug"] = ev.get("league_slug")
                filas.append(parsed)
        except Exception:
            pass

    return pd.DataFrame(filas), df_eventos, eventos_raw


def forzar_consistencia_pronostico(df):
    if df.empty or "Recomendación" not in df.columns:
        return df
    df = df.copy()
    for idx, row in df.iterrows():
        marcador = str(row.get("Resultado probable", ""))
        if marcador in ["0-0", "1-1", "2-2"]:
            df.at[idx, "Recomendación"] = "Empate"
            df.at[idx, "Para prode"] = "Empate"
            if pd.notna(row.get("Prob empate %")):
                df.at[idx, "Confianza %"] = row.get("Prob empate %")
    return df



def odds_api_io_discover_leagues(limit=200, status_filter="pending", force_api=False):
    """
    Trae eventos de football y arma una tabla única de ligas disponibles en Odds-API.io.
    Sirve para descubrir el league_slug real sin adivinar.
    """
    cache_key = f"odds_api_io_leagues::football::{status_filter}::{limit}"

    def fetch():
        params = {
            "apiKey": get_odds_api_io_key(),
            "sport": "football",
            "limit": int(limit),
        }
        if status_filter:
            params["status"] = status_filter
        return odds_api_io_get("/events", params=params, timeout=30)

    data, source = get_or_fetch_cache(
        cache_key,
        CACHE_TTL_HOURS["odds_api_io"],
        fetch_fn=fetch,
        force=force_api
    )

    df_events = parse_odds_api_io_events(data)
    if df_events.empty:
        return pd.DataFrame(), df_events, data

    df_leagues = (
        df_events[["league", "league_slug"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["league", "league_slug"])
        .reset_index(drop=True)
    )

    # Conteo de eventos por liga
    counts = (
        df_events.groupby(["league", "league_slug"], as_index=False)
        .size()
        .rename(columns={"size": "eventos_detectados"})
    )

    df_leagues = df_leagues.merge(counts, on=["league", "league_slug"], how="left")
    return df_leagues, df_events, data


def filtrar_ligas_por_texto(df, texto):
    if df.empty or not texto:
        return df
    t = str(texto).lower().strip()
    return df[
        df["league"].astype(str).str.lower().str.contains(t, na=False)
        | df["league_slug"].astype(str).str.lower().str.contains(t, na=False)
    ]


def cargar_cuotas_odds_api_io_con_status(league_slug="", limit=20, bookmakers="Bet365,Unibet,SingBet", status_filter="pending", force_api=False):
    """
    Igual que cargar_cuotas_odds_api_io_por_eventos, pero soporta status=pending
    para no traer partidos ya resueltos.
    """
    cache_key = f"odds_api_io_events::football::{league_slug}::{status_filter}::{limit}"

    def fetch_events():
        params = {
            "apiKey": get_odds_api_io_key(),
            "sport": "football",
            "limit": int(limit),
        }
        if league_slug:
            params["league"] = league_slug
        if status_filter:
            params["status"] = status_filter
        return odds_api_io_get("/events", params=params, timeout=30)

    eventos_raw, source = get_or_fetch_cache(
        cache_key,
        CACHE_TTL_HOURS["odds_api_io"],
        fetch_fn=fetch_events,
        force=force_api
    )

    df_eventos = parse_odds_api_io_events(eventos_raw)

    if df_eventos.empty:
        return pd.DataFrame(), df_eventos, eventos_raw

    filas = []
    for _, ev in df_eventos.iterrows():
        event_id = ev.get("event_id")
        if not event_id:
            continue

        try:
            raw_odds = odds_api_io_event_odds(event_id, bookmakers, force_api=force_api)
            parsed = parse_odds_api_io_odds_response(raw_odds)
            if parsed:
                parsed["local"] = parsed.get("local") or ev.get("local")
                parsed["visitante"] = parsed.get("visitante") or ev.get("visitante")
                parsed["fecha_api"] = parsed.get("fecha_api") or ev.get("fecha_api")
                parsed["league"] = ev.get("league")
                parsed["league_slug"] = ev.get("league_slug")
                parsed["estado"] = ev.get("estado")
                filas.append(parsed)
        except Exception:
            pass

    return pd.DataFrame(filas), df_eventos, eventos_raw


def cargar_proximo_evento_futbol_odds_api_io(bookmakers="Bet365,Unibet,SingBet", force_api=False):
    """
    Prueba rápida: trae el próximo evento de football disponible en Odds-API.io
    y busca cuotas ML/1X2 para ese evento.
    """
    eventos_raw = odds_api_io_events(league_slug="", limit=1, force_api=force_api)
    df_eventos = parse_odds_api_io_events(eventos_raw)

    if df_eventos.empty:
        return pd.DataFrame(), df_eventos, eventos_raw, None

    ev = df_eventos.iloc[0]
    event_id = ev.get("event_id")

    if not event_id:
        return pd.DataFrame(), df_eventos, eventos_raw, None

    raw_odds = odds_api_io_event_odds(event_id, bookmakers, force_api=force_api)
    parsed = parse_odds_api_io_odds_response(raw_odds)

    if not parsed:
        return pd.DataFrame(), df_eventos, eventos_raw, raw_odds

    parsed["local"] = parsed.get("local") or ev.get("local")
    parsed["visitante"] = parsed.get("visitante") or ev.get("visitante")
    parsed["fecha_api"] = parsed.get("fecha_api") or ev.get("fecha_api")
    parsed["league"] = ev.get("league")
    parsed["league_slug"] = ev.get("league_slug")
    parsed["estado"] = ev.get("estado")

    return pd.DataFrame([parsed]), df_eventos, eventos_raw, raw_odds

st.title("⚽ Prode Odds")
st.caption("Botoncitos rápidos + The Odds API + Liga Argentina real con API-Football.")

odds_key = get_odds_key()
api_football_key = get_api_football_key()
odds_api_io_key = get_odds_api_io_key()

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

    if odds_api_io_key:
        st.success("ODDS_API_IO_KEY detectada.")
    else:
        st.warning("Falta ODDS_API_IO_KEY para cuotas extra.")

    if supabase_enabled():
        st.success("Supabase cache activo.")
    else:
        st.warning("Supabase cache no configurado.")

    st.divider()
    st.header("API-Football Free")
    st.info("Tu plan free permite temporadas 2022, 2023 y 2024. 2025/2026 no están disponibles en free.")

    st.divider()
    st.header("Secrets")
    st.code('ODDS_API_KEY = "tu_key_the_odds_api"\nAPI_FOOTBALL_KEY = "tu_key_api_football"\nODDS_API_IO_KEY = "tu_key_odds_api_io"\nSUPABASE_URL = "https://xxxxx.supabase.co"\nSUPABASE_ANON_KEY = "tu_anon_key"', language="toml")

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

if "cache_status" in st.session_state:
    st.info(st.session_state["cache_status"])

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
    st.caption("Liga Argentina usa API-Football para fixture. En plan free usar temporadas 2022-2024.")

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

            liga_default = encontrar_liga_profesional(df_ligas_arg)
            opciones_ligas = {
                f"{row['league_name']} — ID {row['league_id']} — free: {row['temporadas_free']}": int(row["league_id"])
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
            temporadas_api = fila_liga["seasons"] if isinstance(fila_liga["seasons"], list) else FREE_API_FOOTBALL_SEASONS
            temporadas_free = fila_liga["temporadas_free"] if isinstance(fila_liga["temporadas_free"], list) and fila_liga["temporadas_free"] else [2024, 2023, 2022]

            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                season = st.selectbox("Temporada", temporadas_free, index=0)
            with col2:
                modo_fecha = st.selectbox(
                    "Qué cargar",
                    ["last", "rango"],
                    format_func=lambda x: {"last": "Últimos partidos", "rango": "Rango de fechas"}[x]
                )
            with col3:
                st.info("Free API-Football: temporadas 2022-2024. Para 2026 habría que pagar o usar otra fuente.")

            if modo_fecha == "last":
                cantidad = st.slider("Cantidad de partidos", min_value=5, max_value=50, value=20, step=5)
                desde = hasta = None
            else:
                colf1, colf2 = st.columns(2)
                with colf1:
                    desde_date = st.date_input("Desde", value=date(int(season), 1, 1))
                with colf2:
                    hasta_date = st.date_input("Hasta", value=date(int(season), 12, 31))
                desde = desde_date.isoformat()
                hasta = hasta_date.isoformat()
                cantidad = 20

            force_api_arg = st.checkbox("Forzar actualización desde API-Football", value=False, help="Si está desmarcado usa Supabase si hay datos guardados. Si lo marcás consume request.")

            if st.button("Cargar partidos de Liga Argentina", type="primary"):
                try:
                    if int(season) not in FREE_API_FOOTBALL_SEASONS:
                        st.error("Tu plan free no tiene acceso a esa temporada. Usá 2022, 2023 o 2024.")
                    else:
                        df_fix = cargar_fixtures_api_football(
                            league_id=league_id,
                            season=season,
                            modo_fecha=modo_fecha,
                            cantidad=cantidad,
                            desde=desde,
                            hasta=hasta,
                            force_api=force_api_arg,
                        )

                        if df_fix.empty:
                            st.warning("API-Football respondió, pero no devolvió partidos para esos filtros.")
                        else:
                            st.session_state["df_resultado"] = forzar_consistencia_pronostico(agregar_calculos(df_fix))
                            st.success(f"Partidos cargados: {len(df_fix)}")

                        headers = st.session_state.get("api_football_headers", {})
                        st.caption(f"API-Football límite: {headers.get('requests_limit')} | restantes: {headers.get('requests_remaining')}")

                except Exception as e:
                    st.error(str(e))

            st.subheader("Cuotas Odds-API.io para Argentina")

            if not odds_api_io_key:
                st.warning("Para buscar cuotas en Odds-API.io cargá ODDS_API_IO_KEY en Secrets.")
            else:
                st.markdown("#### Prueba rápida")

                col_p1, col_p2 = st.columns([1, 2])
                with col_p1:
                    force_next_event = st.checkbox(
                        "Forzar próximo evento",
                        value=False,
                        help="Si está desmarcado usa Supabase si ya se guardó."
                    )
                with col_p2:
                    next_bookmakers = st.text_input(
                        "Bookmakers para prueba rápida",
                        value="Bet365,Unibet,SingBet",
                        key="next_bookmakers"
                    )

                if st.button("⚡ Probar próximo evento de fútbol"):
                    try:
                        df_next, df_next_events, raw_next_events, raw_next_odds = cargar_proximo_evento_futbol_odds_api_io(
                            bookmakers=next_bookmakers,
                            force_api=force_next_event
                        )

                        st.session_state["next_event_events"] = df_next_events
                        st.session_state["next_event_raw_events"] = raw_next_events
                        st.session_state["next_event_raw_odds"] = raw_next_odds

                        if df_next_events.empty:
                            st.warning("Odds-API.io no devolvió eventos próximos de fútbol.")
                        elif df_next.empty:
                            st.warning("Encontré el próximo evento, pero no encontré cuotas ML/1X2 para esos bookmakers.")
                            st.dataframe(df_next_events, use_container_width=True)
                        else:
                            st.session_state["df_resultado"] = forzar_consistencia_pronostico(agregar_calculos(df_next))
                            st.success("Prueba cargada: próximo evento + cuotas.")
                    except Exception as e:
                        st.error(str(e))

                if "next_event_events" in st.session_state:
                    with st.expander("Ver próximo evento detectado"):
                        st.dataframe(st.session_state["next_event_events"], use_container_width=True)

                if "next_event_raw_odds" in st.session_state and st.session_state["next_event_raw_odds"] is not None:
                    with st.expander("Ver respuesta cruda cuotas próximo evento"):
                        st.json(st.session_state["next_event_raw_odds"])

                st.markdown("#### A) Descubrir ligas disponibles en Odds-API.io")

                col_d1, col_d2, col_d3 = st.columns([1, 1, 2])
                with col_d1:
                    discover_status = st.selectbox(
                        "Estado eventos",
                        ["pending", "live", "settled", ""],
                        index=0,
                        help="pending = próximos partidos. Vacío = todos."
                    )
                with col_d2:
                    discover_limit = st.slider("Eventos para analizar", 50, 500, 200, 50)
                with col_d3:
                    buscar_liga = st.text_input("Buscar liga", value="argentina", help="Ej: argentina, libertadores, sudamericana, premier")

                force_discover = st.checkbox(
                    "Forzar búsqueda de ligas Odds-API.io",
                    value=False,
                    help="Si está desmarcado usa Supabase si hay cache vigente."
                )

                if st.button("🔍 Buscar ligas disponibles en Odds-API.io"):
                    try:
                        df_leagues, df_events, raw_events = odds_api_io_discover_leagues(
                            limit=discover_limit,
                            status_filter=discover_status,
                            force_api=force_discover
                        )

                        st.session_state["odds_api_io_leagues"] = df_leagues
                        st.session_state["odds_api_io_events_discovery"] = df_events
                        st.session_state["odds_api_io_raw_discovery"] = raw_events

                        if df_leagues.empty:
                            st.warning("Odds-API.io respondió, pero no encontré ligas en los eventos devueltos.")
                        else:
                            st.success(f"Ligas detectadas: {len(df_leagues)}")

                    except Exception as e:
                        st.error(str(e))

                if "odds_api_io_leagues" in st.session_state:
                    ligas_mostrar = filtrar_ligas_por_texto(st.session_state["odds_api_io_leagues"], buscar_liga)

                    with st.expander("Ver ligas detectadas desde Odds-API.io", expanded=True):
                        st.dataframe(ligas_mostrar, use_container_width=True)

                    if not ligas_mostrar.empty:
                        opciones_ligas_io = {
                            f"{row['league']} — {row['league_slug']} — eventos: {row['eventos_detectados']}": row["league_slug"]
                            for _, row in ligas_mostrar.iterrows()
                        }

                        liga_io_label = st.selectbox("Usar esta liga Odds-API.io", list(opciones_ligas_io.keys()))
                        if st.button("Usar slug seleccionado"):
                            st.session_state["odds_api_io_selected_slug"] = opciones_ligas_io[liga_io_label]
                            st.success(f"Slug seleccionado: {st.session_state['odds_api_io_selected_slug']}")

                st.markdown("#### B) Buscar cuotas para una liga")

                slug_default = st.session_state.get("odds_api_io_selected_slug", "argentina-liga-profesional")

                col_o1, col_o2, col_o3 = st.columns([1, 1, 2])
                with col_o1:
                    league_slug_io = st.text_input(
                        "League slug Odds-API.io",
                        value=slug_default,
                        help="Podés elegirlo desde el descubridor de ligas o dejarlo vacío para fútbol general."
                    )
                with col_o2:
                    limit_io = st.slider("Eventos Odds-API.io", 5, 50, 20, 5)
                with col_o3:
                    bookmakers_io = st.text_input("Bookmakers", value="Bet365,Unibet,SingBet")

                col_o4, col_o5 = st.columns([1, 2])
                with col_o4:
                    status_io = st.selectbox("Status", ["pending", "live", "settled", ""], index=0)
                with col_o5:
                    st.caption("pending evita traer partidos ya jugados. Si no encuentra cuotas, probá otros bookmakers o dejá el slug vacío para verificar cobertura.")

                force_api_io = st.checkbox("Forzar Odds-API.io", value=False, help="Si está desmarcado usa Supabase si hay cache vigente.")

                if st.button("Buscar cuotas Odds-API.io"):
                    try:
                        df_odds_io, df_events_io, raw_events_io = cargar_cuotas_odds_api_io_con_status(
                            league_slug=league_slug_io,
                            limit=limit_io,
                            bookmakers=bookmakers_io,
                            status_filter=status_io,
                            force_api=force_api_io
                        )

                        st.session_state["odds_api_io_events"] = df_events_io
                        st.session_state["odds_api_io_raw_events"] = raw_events_io

                        if df_events_io.empty:
                            st.warning("Odds-API.io no devolvió eventos para ese slug/status.")
                        elif df_odds_io.empty:
                            st.warning("Odds-API.io trajo eventos, pero no encontré cuotas ML/1X2 para los bookmakers elegidos.")
                        else:
                            st.session_state["df_odds_api_io"] = df_odds_io

                            if not st.session_state["df_resultado"].empty:
                                cruzado = intentar_cruzar_cuotas_argentina_con_odds_api_io(
                                    st.session_state["df_resultado"],
                                    df_odds_io
                                )
                                st.session_state["df_resultado"] = forzar_consistencia_pronostico(agregar_calculos(cruzado))
                                st.success("Cuotas cruzadas contra el fixture actual.")
                            else:
                                st.session_state["df_resultado"] = forzar_consistencia_pronostico(agregar_calculos(df_odds_io))
                                st.success("Cuotas cargadas desde Odds-API.io.")

                    except Exception as e:
                        st.error(str(e))

                if "odds_api_io_events" in st.session_state:
                    with st.expander("Ver eventos detectados desde Odds-API.io"):
                        st.dataframe(st.session_state["odds_api_io_events"], use_container_width=True)

                if "df_odds_api_io" in st.session_state:
                    with st.expander("Ver cuotas detectadas desde Odds-API.io"):
                        st.dataframe(st.session_state["df_odds_api_io"], use_container_width=True)

                if "odds_api_io_raw_events" in st.session_state:
                    with st.expander("Ver respuesta cruda eventos Odds-API.io"):
                        st.json(st.session_state["odds_api_io_raw_events"])

                if "odds_api_io_events_discovery" in st.session_state:
                    with st.expander("Ver eventos usados para descubrir ligas"):
                        st.dataframe(st.session_state["odds_api_io_events_discovery"], use_container_width=True)

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
            force_api_odds = st.checkbox("Forzar API", value=False, help="Si está desmarcado usa Supabase si hay cache vigente.")
            if st.button("Limpiar resultado"):
                st.session_state["df_resultado"] = pd.DataFrame()
                st.rerun()

        if modo_actual == "h2h":
            if st.button("Actualizar partidos y cuotas", type="primary"):
                try:
                    eventos = consultar_eventos_odds(odds_key, sport_key, ",".join(regions), "h2h", force_api=force_api_odds)
                    df_partidos = eventos_h2h_a_df(eventos, promediar=promediar)

                    if df_partidos.empty:
                        st.warning("La API respondió, pero no encontró partidos/cuotas h2h para esta categoría.")
                        with st.expander("Ver respuesta cruda"):
                            st.json(eventos[:3] if isinstance(eventos, list) else eventos)
                    else:
                        st.session_state["df_resultado"] = forzar_consistencia_pronostico(agregar_calculos(df_partidos))
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
                    eventos = consultar_eventos_odds(odds_key, sport_key, ",".join(regions), "outrights", force_api=force_api_odds)
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
            st.session_state["df_resultado"] = forzar_consistencia_pronostico(agregar_calculos(edited))
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
