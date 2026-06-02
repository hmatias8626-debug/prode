# Prode Mundial - Cruces + Cuotas API

App en Streamlit para cargar cruces del Mundial 2026 desde OpenFootball y traer cuotas desde The Odds API.

## Cómo correr local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Secrets en Streamlit Cloud

En Streamlit Cloud ir a:

Settings → Secrets

Pegar:

```toml
ODDS_API_KEY = "TU_API_KEY"
```

No subas tu API key a GitHub.

## Deploy

1. Crear repo en GitHub.
2. Subir estos archivos.
3. En Streamlit Community Cloud crear app nueva.
4. Main file: `app.py`.
5. Cargar el secret `ODDS_API_KEY`.
