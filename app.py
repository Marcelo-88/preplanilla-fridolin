import streamlit as st
from modules.data_loader import load_sheet_data

# Configuración principal
st.set_page_config(
    page_title="Pre-Planilla Fridolin",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 Sistema de Pre-Planilla - Fridolin")

# Menú lateral ajustado a las pestañas reales
st.sidebar.image("https://em-content.zobj.net/source/apple/354/factory_1f3ed.png", width=80)
st.sidebar.title("Menú Principal")

opcion = st.sidebar.radio(
    "Seleccione una vista:",
    [
        "📊 Parámetros y Reglas",
        "👥 Maestro de Empleados",
        "⏱️ Importación Biométrico",
        "📝 Novedades y Permisos",
        "✅ Aprobaciones Supervisores",
        "📑 Pre-Planilla y Reportes"
    ]
)

st.sidebar.divider()
st.sidebar.caption("Sistema de Control de Asistencia v1.0")

# 1. Parámetros
if opcion == "📊 Parámetros y Reglas":
    st.header("Parámetros y Reglas del Sistema")
    try:
        df_params = load_sheet_data("05_Parametros_y_Reglas")
        st.dataframe(df_params, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña '05_Parametros_y_Reglas': {e}")

# 2. Maestro de Empleados
elif opcion == "👥 Maestro de Empleados":
    st.header("Maestro de Empleados")
    try:
        df_emp = load_sheet_data("01_Maestro_Empleados")
        st.dataframe(df_emp, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña '01_Maestro_Empleados': {e}")

# 3. Importación Biométrico
elif opcion == "⏱️ Importación Biométrico":
    st.header("Registros del Biométrico")
    try:
        df_bio = load_sheet_data("02_Importacion_Biometrico")
        st.dataframe(df_bio, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña '02_Importacion_Biometrico': {e}")

# 4. Novedades y Permisos
elif opcion == "📝 Novedades y Permisos":
    st.header("Novedades y Permisos")
    try:
        df_nov = load_sheet_data("04_Novedades_y_Permisos")
        st.dataframe(df_nov, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña '04_Novedades_y_Permisos': {e}")

# 5. Aprobaciones Supervisores
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("Aprobaciones de Supervisores")
    try:
        df_aprob = load_sheet_data("03_Aprobaciones_Supervisores")
        st.dataframe(df_aprob, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña '03_Aprobaciones_Supervisores': {e}")

# 6. Pre-Planilla (Procesamiento)
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("Generación y Procesamiento de Pre-Planilla")
    st.info("Aquí se procesarán los cálculos cruzando el biométrico con los parámetros.")
