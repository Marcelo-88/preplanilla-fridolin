import streamlit as st
from modules.data_loader import load_sheet_data

# Configuración principal de la aplicación
st.set_page_config(
    page_title="Pre-Planilla Fridolin",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 Sistema de Pre-Planilla - Fridolin")

# Menú lateral de navegación
st.sidebar.image("https://em-content.zobj.net/source/apple/354/factory_1f3ed.png", width=80)
st.sidebar.title("Menú Principal")

opcion = st.sidebar.radio(
    "Seleccione una vista:",
    [
        "📊 Parámetros y Reglas",
        "👥 Personal y Horarios",
        "⏱️ Marcaciones",
        "📑 Pre-Planilla y Reportes"
    ]
)

st.sidebar.divider()
st.sidebar.caption("Sistema de Control de Asistencia v1.0")

# 1. Sección: Parámetros
if opcion == "📊 Parámetros y Reglas":
    st.header("Parámetros y Reglas del Sistema")
    st.write("Configuración de tolerancias, horas de jornada y tiempos de descanso.")
    try:
        df_params = load_sheet_data("Parametros")
        st.dataframe(df_params, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña 'Parametros': {e}")

# 2. Sección: Personal y Horarios
elif opcion == "👥 Personal y Horarios":
    st.header("Gestión de Personal y Turnos")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Lista de Empleados")
        try:
            df_emp = load_sheet_data("Empleados")
            st.dataframe(df_emp, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error al cargar la pestaña 'Empleados': {e}")
            
    with col2:
        st.subheader("Turnos y Horarios")
        try:
            df_horarios = load_sheet_data("Horarios")
            st.dataframe(df_horarios, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error al cargar la pestaña 'Horarios': {e}")

# 3. Sección: Marcaciones
elif opcion == "⏱️ Marcaciones":
    st.header("Registro de Marcaciones Biométricas")
    try:
        df_marcaciones = load_sheet_data("Marcaciones")
        st.dataframe(df_marcaciones, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña 'Marcaciones': {e}")

# 4. Sección: Pre-Planilla (Procesamiento)
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("Generación y Procesamiento de Pre-Planilla")
    st.info("Aquí se mostrarán los cálculos automáticos de atrasos, horas extras y nocturnas (Paso 3).")
