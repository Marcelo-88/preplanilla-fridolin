import streamlit as st
import pandas as pd
import re
import os

LOCAL_EXCEL_PATH = "Estructura_PrePlanilla_Fridolin.xlsx"


def get_sheet_id(url: str) -> str:
    """Extrae el ID del Google Sheet desde la URL completa."""
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    raise ValueError("URL de Google Sheet inválida")


@st.cache_data(ttl=300)
def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    """
    Carga una pestaña de datos. Intenta primero vía Google Sheets API/CSV.
    Si no hay conexión o falla, realiza fallback transparente a archivo local Excel/CSV.
    """
    # Intentar conexión con Google Sheets
    if "gsheets" in st.secrets and "spreadsheet_url" in st.secrets["gsheets"]:
        try:
            sheet_url = st.secrets["gsheets"]["spreadsheet_url"]
            sheet_id = get_sheet_id(sheet_url)
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
            df = pd.read_csv(csv_url)
            if not df.empty:
                return df
        except Exception:
            pass  # Continuar a lectura local si falla la red

    # Fallback local 100% offline
    if os.path.exists(LOCAL_EXCEL_PATH):
        try:
            # Limpiar nombre de pestaña por si viene con prefijos de escape
            clean_sheet = sheet_name.replace('\\', '')
            xls = pd.ExcelFile(LOCAL_EXCEL_PATH)
            for s in xls.sheet_names:
                if clean_sheet.lower() in s.lower():
                    return pd.read_excel(LOCAL_EXCEL_PATH, sheet_name=s)
        except Exception as e:
            st.error(f"Error cargando respaldo local '{sheet_name}': {e}")

    # Devuelve DataFrame vacío con estructura mínima si todo lo demás falla
    return pd.DataFrame()
