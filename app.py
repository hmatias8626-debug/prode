import streamlit as st

st.set_page_config(
    page_title='Prode Mundial 2026',
    page_icon='⚽',
    layout='wide'
)

st.title('⚽ Prode Mundial 2026')

st.success('La aplicación está funcionando correctamente.')

try:
    api_key = st.secrets['ODDS_API_KEY']
    st.info(f'API detectada correctamente: {api_key[:6]}********')
except Exception as e:
    st.error('No encuentro la API Key.')
    st.code(str(e))
