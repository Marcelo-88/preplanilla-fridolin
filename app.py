import streamlit as st
import pandas as pd
import io
from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions, get_canje_summary
from modules.auth_permissions import render_user_selector, filter_dataframe_by_supervisor

st.set_page_config(
    page_title="Pre-Planilla Fridolin",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 Control de Asistencia y Reportes - Fridolin")

st.sidebar.image("https://em-content.zobj.net/source/apple/354/factory_1f3ed.png", width=80)
st.sidebar.title("Menú Principal")

# Cargar Maestro de Empleados para autenticación y PIN
try:
    df_emp_master = load_sheet_data("01_Maestro_Empleados")
    usuario_actual, rol_actual, empleados_permitidos, pin_ok = render_user_selector(df_emp_master)
except Exception as e:
    usuario_actual, rol_actual, empleados_permitidos, pin_ok = "Invitado", "Jefe de Producción", [], True
    st.sidebar.error(f"Error cargando credenciales: {e}")

st.sidebar.divider()

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

# -----------------------------------------------------------------------------
# 1. PARÁMETROS Y REGLAS (PÚBLICO)
# -----------------------------------------------------------------------------
if opcion == "📊 Parámetros y Reglas":
    st.header("Parámetros y Reglas del Sistema")
    try:
        df_params = load_sheet_data("05_Parametros_y_Reglas")
        st.dataframe(df_params, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 2. MAESTRO DE EMPLEADOS (PÚBLICO)
# -----------------------------------------------------------------------------
elif opcion == "👥 Maestro de Empleados":
    st.header("Maestro de Empleados")
    try:
        df_emp = load_sheet_data("01_Maestro_Empleados")
        st.dataframe(df_emp, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 3. IMPORTACIÓN BIOMÉTRICO (PÚBLICO)
# -----------------------------------------------------------------------------
elif opcion == "⏱️ Importación Biométrico":
    st.header("Registros del Biométrico")
    try:
        df_bio = load_sheet_data("02_Importacion_Biometrico")
        st.dataframe(df_bio, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 4. NOVEDADES Y PERMISOS (PÚBLICO)
# -----------------------------------------------------------------------------
elif opcion == "📝 Novedades y Permisos":
    st.header("Novedades, Licencias y Permisos Especiales")
    st.info("💡 Incluye licencias legales, vacaciones y regla especial de Permiso de Lactancia Maternidad.")
    try:
        df_nov = load_sheet_data("04_Novedades_y_Permisos")
        st.dataframe(df_nov, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 5. APROBACIONES SUPERVISORES (🔒 CONTROLADO POR PIN Y SUPERVISOR)
# -----------------------------------------------------------------------------
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Centro de Aprobaciones y Excepciones")

    # VALIDACIÓN DE PIN EXCLUSIVA PARA ESTA PESTAÑA
    if not pin_ok:
        st.warning("🔒 Ingrese su PIN de 4 dígitos en la barra lateral para desbloquear el módulo de Aprobaciones.")
        st.stop()

    # CONTROL DE ESTADO DE REVISIÓN
    if 'estado_revision' not in st.session_state:
        st.session_state['estado_revision'] = 'Pendiente / En Proceso'

    col_rev1, col_rev2, col_rev3 = st.columns([2, 1, 1])
    with col_rev1:
        st.subheader(f"Estado de Revisión: **{st.session_state['estado_revision']}**")
    with col_rev2:
        if st.button("▶️ INICIAR Revisión"):
            st.session_state['estado_revision'] = "En Proceso"
            st.success("Revisión habilitada.")
    with col_rev3:
        if st.button("🔒 FINALIZAR Revisión"):
            st.session_state['estado_revision'] = "Finalizada / Cerrada"
            st.success("Revisión finalizada y bloqueada.")

    st.divider()

    tab_excepciones, tab_canje_masivo, tab_regularizar = st.tabs([
        "🚨 Excepciones Automáticas", 
        "⚖️ Canje Masivo (Bolsa HE x Faltas)", 
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
        df_canje_resumen = get_canje_summary(df_res)

        # FILTRADO EXCLUSIVO POR SUPERVISOR A CARGO
        df_excepciones = filter_dataframe_by_supervisor(df_excepciones, 'Nombre', empleados_permitidos, rol_actual)
        df_canje_resumen = filter_dataframe_by_supervisor(df_canje_resumen, 'Nombre', empleados_permitidos, rol_actual)

    except Exception as e:
        df_excepciones = pd.DataFrame()
        df_canje_resumen = pd.DataFrame()
        st.warning(f"No se pudieron cargar los datos biométricos: {e}")

    # TAB 1: EXCEPCIONES AUTOMÁTICAS
    with tab_excepciones:
        if df_excepciones is not None and not df_excepciones.empty:
            st.subheader("Excepciones Detectadas en el Periodo")
            st.info("💡 Puedes revertir o modificar cualquier decisión seleccionándola en la columna 'Decisión'.")

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
            m2.metric("Faltas Totales", len(df_fil_exc[df_fil_exc['Tipo Excepción'] == 'Falta / Omisión Marcación']))
            m3.metric("Sol. Horas Extras", len(df_fil_exc[df_fil_exc['Tipo Excepción'] == 'Horas Extras']))
            m4.metric("Desfases Ingreso", len(df_fil_exc[df_fil_exc['Tipo Excepción'] == 'Desfase Horario Ingreso']))

            df_edited_exc = st.data_editor(
                df_fil_exc,
                use_container_width=True,
                hide_index=True,
                disabled=["ID", "Nombre", "Fecha", "Tipo Excepción", "Detalle Excepción", "Valor a Revisar"] if st.session_state['estado_revision'] == "Finalizada / Cerrada" else [],
                column_config={
                    "Decisión Supervisor": st.column_config.SelectboxColumn(
                        "Decisión",
                        options=[
                            "Pendiente", 
                            "Aprobado (Pago)", 
                            "Acumular (Próx. Mes)", 
                            "Rechazado", 
                            "Justificado", 
                            "Canjeado"
                        ],
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
            st.subheader("📥 Exportación de Aprobaciones")
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
            st.success("🎉 No se detectaron excepciones pendientes para su personal asignado.")

    # TAB 2: CANJE MASIVO
    with tab_canje_masivo:
        st.subheader("⚖️ Canje Masivo de Horas Extras por Faltas")
        if df_canje_resumen is not None and not df_canje_resumen.empty:
            df_edited_canje = st.data_editor(
                df_canje_resumen,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ID": st.column_config.Column(disabled=True),
                    "Nombre": st.column_config.Column(disabled=True),
                    "Turno Dominante": st.column_config.Column(disabled=True),
                    "Horas Costo por Día": st.column_config.NumberColumn("Costo Día (hrs)", disabled=True, format="%.0f hrs"),
                    "Bolsa HE Acumulada (hrs)": st.column_config.NumberColumn("Bolsa HE (hrs)", disabled=True, format="%.2f hrs"),
                    "Días Máx. Canjeables": st.column_config.NumberColumn("Días Máx.", disabled=True, format="%d días"),
                    "Faltas Registradas": st.column_config.NumberColumn("Faltas Reg.", disabled=True, format="%d días"),
                    "Días a Canjear (Aplicar)": st.column_config.NumberColumn(
                        "Días a Canjear",
                        min_value=0,
                        max_value=10,
                        step=1
                    ),
                    "Estado Canje": st.column_config.SelectboxColumn(
                        "Estado Canje",
                        options=["Sin Aplicar", "Canje Aplicado", "Rechazado por Supervisor"],
                        required=True
                    )
                }
            )

            dias_totales_canjeados = df_edited_canje['Días a Canjear (Aplicar)'].sum()
            c_m1, c_m2 = st.columns(2)
            c_m1.metric("Personal con Bolsa HE / Faltas", len(df_edited_canje))
            c_m2.metric("Total Días Canjeados", f"{int(dias_totales_canjeados)} días")
        else:
            st.info("No hay empleados a su cargo con saldo de horas extras o faltas.")

    # TAB 3: REGULARIZACIÓN MANUAL
    with tab_regularizar:
        st.subheader("Regularizar Marcación Faltante u Olvido")
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

# -----------------------------------------------------------------------------
# 6. PRE-PLANILLA Y REPORTES (PÚBLICO)
# -----------------------------------------------------------------------------
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("Reporte Consolidado de Asistencia para RRHH / Contabilidad")
    
    with st.spinner("Procesando marcaciones, novedades y tiempos..."):
        try:
            df_bio = load_sheet_data("02_Importacion_Biometrico")
            df_params = load_sheet_data("05_Parametros_y_Reglas")
            df_emp = load_sheet_data("01_Maestro_Empleados")
            df_nov = load_sheet_data("04_Novedades_y_Permisos")
                
            df_resultado = process_attendance(df_bio, df_params, df_nov, df_emp)

            if df_resultado is not None and not df_resultado.empty:
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
        except Exception as e:
            st.error(f"Error durante el procesamiento: {e}")
