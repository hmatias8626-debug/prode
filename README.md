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


## Odds-API.io v3: descubridor de ligas

La app ahora permite:
1. Buscar eventos de fútbol en Odds-API.io.
2. Extraer automáticamente `league.name` y `league.slug`.
3. Seleccionar el slug correcto.
4. Consultar cuotas con `/odds` por `eventId`.

Recomendado:
- Status: `pending`
- Buscar liga: `argentina`, `libertadores`, `sudamericana`, etc.


## v4 Próximo evento

Agregado botón:
- `⚡ Probar próximo evento de fútbol`

Flujo:
1. `/events?apiKey=...&sport=football&limit=1`
2. `/odds?apiKey=...&eventId=...&bookmakers=...`
3. Calcula probabilidades y muestra resultado.


## Fix bookmakers Odds-API.io

El plan free de Odds-API.io permite máximo 2 bookmakers.
Bookmakers por defecto:

```text
Bet365,888Sport IT
```


## v5 Próximo evento pendiente

Corregido:
- El botón de prueba rápida ahora consulta `/events` con `status=pending`.
- Filtra fechas futuras.
- Prueba hasta 20 eventos futuros hasta encontrar cuotas.
- Ya no debería tomar partidos finalizados/settled.


## v6 Modo ahorro de requests

Cambio principal:
- La app NO consulta APIs externas automáticamente.
- Si no marcás `Forzar API / actualizar`, solo lee desde Supabase.
- Si no hay datos guardados, muestra aviso y no gasta request.
- Si marcás forzar, consulta API y guarda el resultado en Supabase.

Estrategia recomendada:
- Fixture: actualizar una vez y guardar.
- Cuotas: actualizar manualmente cuando te interese.


## v7 Tarjeta de próximo evento

Agregado:
- Tarjeta superior con próximo evento de la competencia seleccionada.
- No consume requests.
- Usa `df_resultado` cargado desde Supabase o actualizado manualmente.
- Muestra fecha/hora Argentina, liga, equipos, cuotas y pronóstico si existen.
