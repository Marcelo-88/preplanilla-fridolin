import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# Alcances requeridos para Google Sheets y Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_gspread_client():
    """Autentica y devuelve el cliente de gspread utilizando los secretos de Streamlit."""
    credentials_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(
        credentials_dict, 
        scopes=SCOPES
    )
    return gspread.authorize(credentials)

@st.cache_data(ttl=300)  # Caché de 5 minutos para optimizar lecturas
def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    """Carga una pestaña específica de Google Sheets en un DataFrame de pandas."""
    client = get_gspread_client()
    spreadsheet = client.open_by_url(st.secrets["gsheets"]["spreadsheet_url"])
    worksheet = spreadsheet.worksheet(sheet_name)
    data = worksheet.get_all_records()
    return pd.DataFrame(data)
