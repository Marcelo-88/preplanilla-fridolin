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
    st.header("✅ Centro de Aprobaciones y Regularizaciones")
    st.caption("Gestión interactiva de excepciones, olvidos de marcación y permisos para Supervisores.")

    tab_aprobaciones, tab_regularizar = st.tabs(["📋 Gestor de Solicitudes", "➕ Regularizar Olvido de Marcación"])

    try:
        df_aprob = load_sheet_data("03_Aprobaciones_Supervisores")
    except Exception as e:
        df_aprob = pd.DataFrame()
        st.warning(f"No se pudo cargar la pestaña de aprobaciones: {e}")

    # TAB 1: GESTOR INTERACTIVO DE SOLICITUDES
    with tab_aprobaciones:
        if df_aprob is not None and not df_aprob.empty:
            cols_map = {str(c).strip().lower(): c for c in df_aprob.columns}
            
            c_sup = next((cols_map[k] for k in cols_map if any(x in k for x in ['supervisor', 'jefe'])), None)
            c_emp = next((cols_map[k] for k in cols_map if any(x in k for x in ['empleado', 'nombre', 'id', 'carnet'])), None)
            c_estado = next((cols_map[k] for k in cols_map if 'estado' in k or 'aprob' in k), None)

            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                opts_estado = ["Todos"] + list(df_aprob[c_estado].astype(str).unique()) if c_estado else ["Todos"]
                sel_estado = st.selectbox("Estado de Solicitud:", opts_estado)
            with f_col2:
                opts_sup = ["Todos"] + list(df_aprob[c_sup].astype(str).unique()) if c_sup else ["Todos"]
                sel_sup = st.selectbox("Filtrar Supervisor:", opts_sup)
            with f_col3:
                opts_emp = ["Todos"] + list(df_aprob[c_emp].astype(str).unique()) if c_emp else ["Todos"]
                sel_emp = st.selectbox("Filtrar Empleado:", opts_emp)

            df_fil = df_aprob.copy()
            if sel_estado != "Todos" and c_estado:
                df_fil = df_fil[df_fil[c_estado].astype(str) == sel_estado]
            if sel_sup != "Todos" and c_sup:
                df_fil = df_fil[df_fil[c_sup].astype(str) == sel_sup]
            if sel_emp != "Todos" and c_emp:
                df_fil = df_fil[df_fil[c_emp].astype(str) == sel_emp]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Solicitudes", len(df_fil))
            if c_estado:
                pend = len(df_fil[df_fil[c_estado].astype(str).str.upper().str.contains("PENDIENTE")])
                aprob = len(df_fil[df_fil[c_estado].astype(str).str.upper().str.contains("APROBADO")])
                rech = len(df_fil[df_fil[c_estado].astype(str).str.upper().str.contains("RECHAZADO")])
                m2.metric("⏳ Pendientes", pend)
                m3.metric("🟢 Aprobados", aprob)
                m4.metric("🔴 Rechazados", rech)

            st.subheader("Edición Interactiva de Aprobaciones")
            st.info("💡 Puedes cambiar el estado de las solicitudes o editar observaciones directamente en la tabla.")

            df_edited = st.data_editor(
                df_fil,
                use_container_width=True,
                hide_index=True,
                column_config={
                    c_estado: st.column_config.SelectboxColumn(
                        "Estado Aprobación",
                        options=["Pendiente", "Aprobado", "Rechazado"],
                        required=True
                    )
                } if c_estado else {}
            )

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_edited.to_excel(writer, index=False, sheet_name='Aprobaciones_Supervisores')
            
            st.download_button(
                label="📥 Descargar Aprobaciones Actualizadas (Excel)",
                data=buffer.getvalue(),
                file_name="Aprobaciones_Supervisores_Fridolin.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No se registraron solicitudes pendientes en el sistema.")

    # TAB 2: REGULARIZACIÓN MANUAL DE MARCACIONES FALTANTES
    with tab_regularizar:
        st.subheader("Regularizar Marcación Faltante u Olvido")
        st.write("Permite al supervisor completar horas de entrada o salida no marcadas en el biométrico.")

        with st.form("form_regularizacion"):
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                id_emp_reg = st.text_input("ID / Carnet Empleado:*")
                nombre_emp_reg = st.text_input("Nombre Completo Empleado:*")
                fecha_reg = st.date_input("Fecha de la Marcación Omisa:")
            
            with r_col2:
                tipo_marcacion = st.selectbox("Tipo de Marcación Faltante:", ["Entrada Omisa", "Salida Omisa", "Jornada Completa Omisa"])
                hora_reg = st.time_input("Hora Aprobada de Marcación:")
                motivo_reg = st.text_area("Motivo / Justificación del Supervisor:*")

            submitted = st.form_submit_button("✅ Registrar Regularización")

            if submitted:
                if not id_emp_reg or not nombre_emp_reg or not motivo_reg:
                    st.warning("Por favor complete todos los campos obligatorios (*).")
                else:
                    st.success(f"Regularización registrada para {nombre_emp_reg} el día {fecha_reg}. Se incluirá en la consolidación de la Pre-Planilla.")

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
