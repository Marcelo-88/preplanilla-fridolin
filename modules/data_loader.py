import streamlit as st
import pandas as pd
import re

def get_sheet_id(url: str) -> str:
    """Extrae el ID del Google Sheet desde la URL completa."""
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    raise ValueError("URL de Google Sheet inválida")

@st.cache_data(ttl=300)
def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    """Carga una pestaña de Google Sheets mediante exportación CSV."""
    sheet_url = st.secrets["gsheets"]["spreadsheet_url"]
    sheet_id = get_sheet_id(sheet_url)
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    return pd.read_csv(csv_url)
