import streamlit as st
import pandas as pd
import io
from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions

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
    st.header("✅ Centro de Aprobaciones y Excepciones")
    st.caption("Panel dinámico para revisión de faltas, horas extras, 7º día y canje de compensaciones.")

    tab_excepciones, tab_canje, tab_regularizar = st.tabs([
        "🚨 Excepciones Automáticas", 
        "⚖️ Canje HE por Faltas", 
        "➕ Regularizar Olvido Marcación"
    ])

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

        df_res = process_attendance(df_bio, df_params, df_nov, df_emp)
        df_excepciones = detect_exceptions(df_res)
    except Exception as e:
        df_excepciones = pd.DataFrame()
        st.warning(f"No se pudieron cargar los datos biométricos para calcular excepciones: {e}")

    with tab_excepciones:
        if df_excepciones is not None and not df_excepciones.empty:
            st.subheader("Excepciones Detectadas en el Periodo")
            st.info("💡 Haz clic sobre las celdas de 'Decisión' o 'Tipo Falta' para cambiar su estado (Aprobado, Rechazado, Justificada, Injustificada).")

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                tipo_exc = ["Todos"] + list(df_excepciones['Tipo Excepción'].unique())
                sel_tipo = st.selectbox("Filtrar por Tipo de Excepción:", tipo_exc)
            with col_f2:
                emps = ["Todos"] + list(df_excepciones['Nombre'].unique())
                sel_emp_exc = st.selectbox("Filtrar por Empleado:", emps)

            df_fil_exc = df_excepciones.copy()
            if sel_tipo != "Todos":
                df_fil_exc = df_fil_exc[df_fil_exc['Tipo Excepción'] == sel_tipo]
            if sel_emp_exc != "Todos":
                df_fil_exc = df_fil_exc[df_fil_exc['Nombre'] == sel_emp_exc]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Excepciones Totales", len(df_fil_exc))
            m2.metric("Faltas Totales (A Reportar)", len(df_fil_exc[df_fil_exc['Tipo Excepción'] == 'Falta / Omisión Marcación']))
            m3.metric("Sol. Horas Extras", len(df_fil_exc[df_fil_exc['Tipo Excepción'] == 'Horas Extras']))
            m4.metric("7º Día / Desfases", len(df_fil_exc[df_fil_exc['Tipo Excepción'].isin(['7º Día Laborado', 'Desfase Horario Ingreso'])]))

            df_edited_exc = st.data_editor(
                df_fil_exc,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Decisión Supervisor": st.column_config.SelectboxColumn(
                        "Decisión",
                        options=["Pendiente", "Aprobado", "Rechazado", "Justificado", "Canjeado"],
                        required=True
                    ),
                    "Tipo Falta": st.column_config.SelectboxColumn(
                        "Tipo Falta (Para Contabilidad)",
                        options=["N/A", "Justificada", "Injustificada"],
                        required=True
                    ),
                    "Observaciones": st.column_config.TextColumn(
                        "Observaciones / Motivo",
                        width="medium"
                    )
                }
            )

            st.divider()
            st.subheader("📥 Exportación 'Copy-Paste Ready' para Google Drive")
            st.caption("Descarga este Excel con las clasificaciones ajustadas para enviarlo a Contabilidad.")

            buffer_exc = io.BytesIO()
            with pd.ExcelWriter(buffer_exc, engine='openpyxl') as writer:
                df_edited_exc.to_excel(writer, index=False, sheet_name='03_Aprobaciones_Supervisores')

            st.download_button(
                label="📥 Descargar Aprobaciones Procesadas (Excel)",
                data=buffer_exc.getvalue(),
                file_name="03_Aprobaciones_Supervisores_CopyPaste.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.success("🎉 No se detectaron excepciones pendientes de revisión.")

    with tab_canje:
        st.subheader("⚖️ Compensación y Canje de Bolsa de Horas Extras por Faltas")
        st.write("Permite cancelar 1 Falta utilizando la bolsa de Horas Extras acumuladas del empleado.")

        if df_res is not None and not df_res.empty:
            df_canje_summary = df_res.groupby(['ID', 'Nombre']).agg(
                Total_HE=('Horas Extras', 'sum'),
                Horas_Trabajadas=('Horas Trabajadas', 'sum')
            ).reset_index()

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                emp_canje_sel = st.selectbox("Seleccione Empleado para Canje:", df_canje_summary['Nombre'].unique())
            
            info_emp = df_canje_summary[df_canje_summary['Nombre'] == emp_canje_sel].iloc[0]
            
            with col_c2:
                st.metric("Bolsa HE Disponibles", f"{info_emp['Total_HE']:.2f} hrs")

            with st.form("form_canje_he"):
                st.write(f"**Empleado:** {info_emp['Nombre']} (ID: {info_emp['ID']})")
                fecha_falta_canje = st.date_input("Fecha de la Falta a Compensar:")
                he_a_canjear = st.number_input("Horas Extras a Descontar (Ej: 8.0 hrs por 1 día de falta):", min_value=1.0, max_value=24.0, value=8.0, step=0.5)
                obs_canje = st.text_area("Justificación del Canje / Autorización:")

                submit_canje = st.form_submit_button("🔄 Aplicar Canje de Horas Extras")

                if submit_canje:
                    if info_emp['Total_HE'] < he_a_canjear:
                        st.error(f"El empleado solo cuenta con {info_emp['Total_HE']:.2f} hrs extras. No alcanza para compensar {he_a_canjear} hrs.")
                    else:
                        st.success(f"✅ Canje exitoso: Se descontarán {he_a_canjear} hrs HE para la falta del día {fecha_falta_canje}.")
        else:
            st.info("Cargue los datos biométricos para habilitar la calculadora de canjes.")

    with tab_regularizar:
        st.subheader("Regularizar Marcación Faltante u Olvido")
        st.write("Permite al supervisor completar horas de entrada o salida no marcadas en el biométrico.")

        with st.form("form_regularizacion_panel"):
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
                    st.success(f"Regularización registrada para {nombre_emp_reg} el día {fecha_reg}.")

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
                
                c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
                c1.metric("Registros", len(df_filtrado))
                c2.metric("Horas Trabajadas", f"{df_filtrado['Horas Trabajadas'].sum():.2f} hrs")
                c3.metric("Total Atrasos", f"{df_filtrado['Atraso (Minutos)'].sum()} min")
                c4.metric("Horas Extras", f"{df_filtrado['Horas Extras'].sum():.2f} hrs")
                c5.metric("Faltas Justif.", int(df_filtrado['Falta Justificada'].sum()))
                c6.metric("Faltas Injustif.", int(df_filtrado['Falta Injustificada'].sum()))
                c7.metric("Turnos Comp.", f"{df_filtrado['Turnos Computados'].sum():.1f}")
                
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
