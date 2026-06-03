# Prode Odds + Liga Argentina v2

Cambios:
- API-Football free ajustado a temporadas 2022, 2023 y 2024.
- Mejor fórmula de resultado probable: ahora puede recomendar empates y marcadores más variados.
- Liga Argentina trae fixtures desde API-Football.
- Las cuotas siguen editables manualmente.

## Secrets

En Streamlit Cloud → Settings → Secrets:

```toml
ODDS_API_KEY = "TU_KEY_THE_ODDS_API"
API_FOOTBALL_KEY = "TU_KEY_API_FOOTBALL"
ODDS_API_IO_KEY = "TU_KEY_ODDS_API_IO"
```


## Odds-API.io

La app incluye integración flexible para Odds-API.io. Como algunas cuentas/dashboards muestran endpoints distintos, se prueban varias rutas comunes.

Secrets opcionales si tu dashboard informa una URL exacta:

```toml
ODDS_API_IO_BASE_URL = "https://api.odds-api.io"
ODDS_API_IO_EVENTS_ENDPOINT = "/v1/odds"
```


## Supabase cache

Crear esta tabla en Supabase SQL Editor:

```sql
create table if not exists api_cache (
  cache_key text primary key,
  payload jsonb not null,
  created_at timestamptz not null default now()
);
```

Secrets:

```toml
SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_ANON_KEY = "tu_anon_key"
```

También podés usar `SUPABASE_SERVICE_KEY`, pero para una app pública conviene usar anon key con políticas adecuadas.


## Odds-API.io corregido

Usa el flujo correcto:
- `/events?apiKey=...&sport=football&league=...&limit=...`
- `/odds?apiKey=...&eventId=...&bookmakers=Bet365,Unibet,SingBet`

Secret recomendado:

```toml
ODDS_API_IO_BASE_URL = "https://api.odds-api.io/v3"
```

Para probar Argentina:
- `argentina-liga-profesional`
- o dejar vacío el league slug para ver eventos de fútbol disponibles.
