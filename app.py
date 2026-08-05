import streamlit as st
import pandas as pd
import io
from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance

st.set_page_config(
    page_title="Pre-Planilla Fridolin",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 Sistema de Pre-Planilla - Fridolin")

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

if opcion == "📊 Parámetros y Reglas":
    st.header("Parámetros y Reglas del Sistema")
    try:
        df_params = load_sheet_data("05_Parametros_y_Reglas")
        st.dataframe(df_params, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

elif opcion == "👥 Maestro de Empleados":
    st.header("Maestro de Empleados")
    try:
        df_emp = load_sheet_data("01_Maestro_Empleados")
        st.dataframe(df_emp, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

elif opcion == "⏱️ Importación Biométrico":
    st.header("Registros del Biométrico")
    try:
        df_bio = load_sheet_data("02_Importacion_Biometrico")
        st.dataframe(df_bio, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

elif opcion == "📝 Novedades y Permisos":
    st.header("Novedades y Permisos")
    try:
        df_nov = load_sheet_data("04_Novedades_y_Permisos")
        st.dataframe(df_nov, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

elif opcion == "✅ Aprobaciones Supervisores":
    st.header("Aprobaciones de Supervisores")
    try:
        df_aprob = load_sheet_data("03_Aprobaciones_Supervisores")
        st.dataframe(df_aprob, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("Generación y Procesamiento de Pre-Planilla")
    
    with st.spinner("Procesando datos del biométrico..."):
        try:
            df_bio = load_sheet_data("02_Importacion_Biometrico")
            df_params = load_sheet_data("05_Parametros_y_Reglas")
            
            df_resultado = process_attendance(df_bio, df_params)
            
            if not df_resultado.empty:
                # Filtro por Empleado
                empleados = ["Todos"] + list(df_resultado['Nombre'].unique())
                emp_sel = st.selectbox("Filtrar por Empleado:", empleados)
                
                df_filtrado = df_resultado.copy()
                if emp_sel != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['Nombre'] == emp_sel]
                
                st.subheader("Resumen de Asistencia Procesada")
                st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
                
                # Resumen de métricas
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Días Procesados", len(df_filtrado))
                col2.metric("Total Horas Trabajadas", f"{df_filtrado['Horas Trabajadas'].sum():.2f} hrs")
                col3.metric("Total Minutos Atraso", f"{df_filtrado['Atraso (Minutos)'].sum()} min")
                
                # Función para generar descarga Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_filtrado.to_excel(writer, index=False, sheet_name='Pre-Planilla')
                
                st.download_button(
                    label="📥 Descargar Reporte en Excel",
                    data=buffer.getvalue(),
                    file_name="PrePlanilla_Fridolin.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("No hay datos disponibles para procesar.")
        except Exception as e:
            st.error(f"Error durante el procesamiento: {e}")
