import streamlit as st
import pandas as pd
import re

def get_sheet_id(url: str) -> str:
    """Extrae el ID del Google Sheet desde la URL completa."""
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    raise ValueError("URL de Google Sheet inválida")

def clean_ci_str(val) -> str:
    """Limpia y normaliza el Carnet de Identidad eliminando ceros flotantes y espacios."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    s = re.sub(r"\.0+$", "", s)
    return s

@st.cache_data(ttl=300)
def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    """
    Carga una pestaña de Google Sheets mediante exportación CSV.
    Normaliza los nombres de columna y asegura que el Carnet_Identidad sea tratado como texto limpio sin decimales.
    """
    sheet_url = st.secrets["gsheets"]["spreadsheet_url"]
    sheet_id = get_sheet_id(sheet_url)
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    
    df = pd.read_csv(csv_url, dtype=str)
    df.columns = [str(col).strip() for col in df.columns]

    # Normalizar columna de Carnet de Identidad
    for col in df.columns:
        col_clean = col.lower().replace(" ", "_").replace("\\", "")
        if any(x in col_clean for x in ["carnet", "ci", "id_empleado", "codigo"]):
            df[col] = df[col].apply(clean_ci_str)
            df.rename(columns={col: "Carnet_Identidad"}, inplace=True)
            break

    return df
