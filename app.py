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

st.title("🏭 Control de Asistencia y Reportes - Fridolin")

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
    st.header("✅ Centro de Aprobaciones de Supervisores")
    
    try:
        df_aprob = load_sheet_data("03_Aprobaciones_Supervisores")
        
        if df_aprob is not None and not df_aprob.empty:
            cols_cand = [c for c in df_aprob.columns if 'ESTADO' in str(c).upper() or 'APROB' in str(c).upper()]
            col_estado_list = [c for c in cols_cand if 'RETRASO' not in str(c).upper() and 'FALTA' not in str(c).upper()]
            col_estado = col_estado_list if col_estado_list else cols_cand
            
            col_sup = [c for c in df_aprob.columns if 'SUPERVISOR' in str(c).upper() or 'JEFE' in str(c).upper()]
            col_emp = [c for c in df_aprob.columns if 'EMPLEADO' in str(c).upper() or 'NOMBRE' in str(c).upper() or 'ID' in str(c).upper() or 'CARNET' in str(c).upper()]
            
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                opciones_estado = ["Todos"]
                if col_estado:
                    opciones_estado += list(df_aprob[col_estado[0]].astype(str).unique())
                estado_sel = st.selectbox("Filtrar por Estado:", opciones_estado)
                
            with col_f2:
                opciones_sup = ["Todos"]
                if col_sup:
                    opciones_sup += list(df_aprob[col_sup[0]].astype(str).unique())
                sup_sel = st.selectbox("Filtrar por Supervisor:", opciones_sup)
                
            with col_f3:
                opciones_emp = ["Todos"]
                if col_emp:
                    opciones_emp += list(df_aprob[col_emp[0]].astype(str).unique())
                emp_sel = st.selectbox("Filtrar por Empleado:", opciones_emp)
            
            df_fil = df_aprob.copy()
            if estado_sel != "Todos" and col_estado:
                df_fil = df_fil[df_fil[col_estado[0]].astype(str) == estado_sel]
            if sup_sel != "Todos" and col_sup:
                df_fil = df_fil[df_fil[col_sup[0]].astype(str) == sup_sel]
            if emp_sel != "Todos" and col_emp:
                df_fil = df_fil[df_fil[col_emp[0]].astype(str) == emp_sel]
                
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Registros", len(df_fil))
            
            if col_estado:
                col_target = col_estado[0]
                pendientes = len(df_fil[df_fil[col_target].astype(str).str.upper().str.contains("PENDIENTE")])
                aprobados = len(df_fil[df_fil[col_target].astype(str).str.upper().str.contains("APROBADO")])
                rechazados = len(df_fil[df_fil[col_target].astype(str).str.upper().str.contains("RECHAZADO")])
                
                m2.metric("⏳ Pendientes", pendientes)
                m3.metric("🟢 Aprobados", aprobados)
                m4.metric("🔴 Rechazados", rechazados)
            else:
                m2.metric("⏳ Pendientes", 0)
                m3.metric("🟢 Aprobados", 0)
                m4.metric("🔴 Rechazados", 0)

            st.subheader("Listado de Aprobaciones")
            st.dataframe(df_fil, use_container_width=True, hide_index=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_fil.to_excel(writer, index=False, sheet_name='Aprobaciones')
            
            st.download_button(
                label="📥 Descargar Registro de Aprobaciones (Excel)",
                data=buffer.getvalue(),
                file_name="Aprobaciones_Supervisores_Fridolin.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("La pestaña de Aprobaciones de Supervisores se encuentra vacía por el momento.")
            
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("Reporte Consolidado de Asistencia para RRHH / Contabilidad")
    
    with st.spinner("Procesando marcaciones y tiempos..."):
        try:
            df_bio = load_sheet_data("02_Importacion_Biometrico")
            df_params = load_sheet_data("05_Parametros_y_Reglas")
            
            try:
                df_emp = load_sheet_data("01_Maestro_Empleados")
            except Exception:
                df_emp = None
                
            try:
                df_nov = load_sheet_data("04_Novedades_y_Permisos")
            except Exception:
                df_nov = None
                
            df_resultado = process_attendance(df_bio, df_params, df_nov, df_emp)
            
            if not df_resultado.empty:
                col_filtro1, col_filtro2 = st.columns(2)
                
                with col_filtro1:
                    empleados = ["Todos"] + list(df_resultado['Nombre'].unique())
                    emp_sel = st.selectbox("Filtrar por Empleado:", empleados)
                
                with col_filtro2:
                    turnos = ["Todos", "Diurno", "Nocturno"]
                    turno_sel = st.selectbox("Filtrar por Turno:", turnos)
                
                df_filtrado = df_resultado.copy()
                if emp_sel != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['Nombre'] == emp_sel]
                if turno_sel != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['Turno Dominante'] == turno_sel]
                
                st.subheader("Planilla de Control de Tiempos")
                st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
                
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                col1.metric("Registros", len(df_filtrado))
                col2.metric("Horas Trabajadas", f"{df_filtrado['Horas Trabajadas'].sum():.2f} hrs")
                col3.metric("Total Atrasos", f"{df_filtrado['Atraso (Minutos)'].sum()} min")
                col4.metric("Horas Extras", f"{df_filtrado['Horas Extras'].sum():.2f} hrs")
                col5.metric("Turnos Computados", f"{df_filtrado['Turnos Computados'].sum():.1f}")
                col6.metric("Horas Nocturnas", f"{df_filtrado['Horas Nocturnas'].sum():.2f} hrs")
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_filtrado.to_excel(writer, index=False, sheet_name='Reporte_Asistencia')
                
                st.download_button(
                    label="📥 Descargar Reporte de Asistencia (Excel)",
                    data=buffer.getvalue(),
                    file_name="Reporte_Asistencia_Fridolin.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("No hay datos disponibles para procesar.")
        except Exception as e:
            st.error(f"Error durante el procesamiento: {e}")
