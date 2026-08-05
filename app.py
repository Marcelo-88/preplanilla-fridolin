import streamlit as st
from modules.data_loader import load_sheet_data

st.set_page_config(page_title="Sistema Pre-Planilla Fridolin", layout="wide")

st.title("🏭 Sistema de Pre-Planilla - Fridolin")
st.subheader("Prueba de Conexión a Google Sheets")

# Intentar cargar la pestaña de parámetros como prueba
try:
    df_parametros = load_sheet_data("05_Parametros_y_Reglas")
    st.success("¡Conexión exitosa con Google Sheets!")
    st.write("### Parámetros y Reglas cargados:")
    st.dataframe(df_parametros)
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
