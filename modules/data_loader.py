import streamlit as st
import pandas as pd
import re
import os

LOCAL_EXCEL_PATH = "Estructura_PrePlanilla_Fridolin.xlsx"


def clean_ci_val(val) -> str:
    """Función auxiliar para limpiar valores de Carnet de Identidad convirtiéndolos a texto entero sin .0"""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null"):
        return ""
    if s.endswith(".0"):
        return s[:-2].strip()
    try:
        if "." in s:
            f = float(s)
            if f.is_integer():
                return str(int(f)).strip()
    except (ValueError, TypeError):
        pass
    return s


def _sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Sanea automáticamente las columnas de Carnet de Identidad en DataFrames cargados."""
    if df.empty:
        return df
    
    ci_cols = [
        c for c in df.columns 
        if str(c).strip().lower() in ['carnet_identidad', 'carnet', 'ci', 'id', 'id_empleado', 'carnet identidad']
    ]
    for col in ci_cols:
        df[col] = df[col].apply(clean_ci_val)
    return df


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
    df = pd.DataFrame()

    # Intentar conexión con Google Sheets
    if "gsheets" in st.secrets and "spreadsheet_url" in st.secrets["gsheets"]:
        try:
            sheet_url = st.secrets["gsheets"]["spreadsheet_url"]
            sheet_id = get_sheet_id(sheet_url)
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
            df_csv = pd.read_csv(csv_url)
            if not df_csv.empty:
                return _sanitize_dataframe(df_csv)
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
                    df_excel = pd.read_excel(LOCAL_EXCEL_PATH, sheet_name=s)
                    return _sanitize_dataframe(df_excel)
        except Exception as e:
            st.error(f"Error cargando respaldo local '{sheet_name}': {e}")

    # Devuelve DataFrame vacío con estructura limpia si todo lo demás falla
    return _sanitize_dataframe(df)
