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

# Inicialización de estado de sesión para Novedades
if 'novedades_registradas' not in st.session_state:
    st.session_state['novedades_registradas'] = []

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
        "📋 Novedades y Permisos",
        "✅ Aprobaciones Supervisores",
        "📑 Pre-Planilla y Reportes"
    ]
)

st.sidebar.divider()
st.sidebar.caption("Sistema de Control de Asistencia v1.0")

# Función auxiliar para obtener Novedades Combinadas (Sheets + Sesión Actual)
def obtener_novedades_consolidadas():
    lista_novs = []
    try:
        df_nov_sheets = load_sheet_data("04_Novedades_y_Permisos")
        if df_nov_sheets is not None and not df_nov_sheets.empty:
            lista_novs.append(df_nov_sheets)
    except Exception:
        pass

    if st.session_state['novedades_registradas']:
        lista_novs.append(pd.DataFrame(st.session_state['novedades_registradas']))

    if lista_novs:
        return pd.concat(lista_novs, ignore_index=True)
    return None

# Función auxiliar para obtener Parámetros
def cargar_parametros():
    try:
        return load_sheet_data("05_Parametros_y_Reglas")
    except Exception:
        try:
            return load_sheet_data("00_Parametros_Reglas")
        except Exception:
            return None

# -----------------------------------------------------------------------------
# 1. PARÁMETROS Y REGLAS (PÚBLICO)
# -----------------------------------------------------------------------------
if opcion == "📊 Parámetros y Reglas":
    st.header("Parámetros y Reglas del Sistema")
    try:
        df_params = cargar_parametros()
        if df_params is not None and not df_params.empty:
            cols_vis = [c for c in df_params.columns if not str(c).startswith('Unnamed')]
            st.dataframe(df_params[cols_vis], use_container_width=True, hide_index=True)
        else:
            st.info("No se encontraron datos de parámetros y reglas.")
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 2. MAESTRO DE EMPLEADOS (PÚBLICO - CON SEGURIDAD Y LIMPIEZA DE PIN)
# -----------------------------------------------------------------------------
elif opcion == "👥 Maestro de Empleados":
    st.header("Maestro de Empleados")
    try:
        df_emp = load_sheet_data("01_Maestro_Empleados")
        
        if df_emp is not None and not df_emp.empty:
            cols_visibles = [c for c in df_emp.columns if not str(c).startswith('Unnamed')]
            cols_visibles = [c for c in cols_visibles if str(c).strip().upper() != 'PIN']
            st.dataframe(df_emp[cols_visibles], use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos disponibles en el Maestro de Empleados.")
            
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 3. IMPORTACIÓN BIOMÉTRICO (PÚBLICO)
# -----------------------------------------------------------------------------
elif opcion == "⏱️ Importación Biométrico":
    st.header("Registros del Biométrico")
    try:
        df_bio = load_sheet_data("02_Importacion_Biometrico")
        if df_bio is not None and not df_bio.empty:
            cols_vis = [c for c in df_bio.columns if not str(c).startswith('Unnamed')]
            st.dataframe(df_bio[cols_vis], use_container_width=True, hide_index=True)
        else:
            st.info("No hay registros biométricos disponibles.")
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 4. NOVEDADES Y PERMISOS (FORMULARIO INTERACTIVO Y REGLAS DE IMPACTO)
# -----------------------------------------------------------------------------
elif opcion == "📋 Novedades y Permisos":
    st.header("Gestión de Novedades, Licencias y Permisos")
    
    rol_str = str(rol_actual).lower()
    es_autorizado = any(k in rol_str for k in ['supervisor', 'jefatura', 'responsable', 'operaciones', 'admin', 'producción', 'produccion'])

    if not pin_ok or not es_autorizado:
        st.error("⛔ Acceso restringido. Solo Supervisores, Jefatura o Administradores con PIN activo pueden registrar novedades.")
    else:
        st.success(f"🔓 Sesión Autorizada: **{usuario_actual}** ({rol_actual})")
        
        try:
            df_emp = load_sheet_data("01_Maestro_Empleados")
        except Exception:
            df_emp = None

        if df_emp is not None and not df_emp.empty:
            cols_map = {str(c).strip().lower(): c for c in df_emp.columns}
            col_nom = next((cols_map[k] for k in cols_map if 'nombre' in k or 'empleado' in k), df_emp.columns[0])
            col_sup = next((cols_map[k] for k in cols_map if 'supervisor' in k), None)

            if col_sup and not any(k in rol_str for k in ['responsable', 'admin', 'operaciones']):
                personal_lista = df_emp[df_emp[col_sup].astype(str).str.upper() == str(usuario_actual).upper()][col_nom].dropna().unique().tolist()
                if not personal_lista:
                    personal_lista = df_emp[col_nom].dropna().unique().tolist()
            else:
                personal_lista = df_emp[col_nom].dropna().unique().tolist()

            with st.expander("➕ Registrar Nueva Novedad / Licencia / Maternidad", expanded=True):
                with st.form(key="form_novedades"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        emp_seleccionado = st.selectbox("Seleccione el Empleado:", options=sorted(personal_lista))
                        tipo_permiso = st.selectbox(
                            "Tipo de Novedad / Licencia:",
                            options=[
                                "Baja Médica",
                                "Licencia",
                                "Permiso",
                                "Maternidad (Lactancia)"
                            ]
                        )
                    
                    with col2:
                        fechas = st.date_input("Rango de Fechas (Desde - Hasta):", value=[pd.to_datetime("today"), pd.to_datetime("today")])
                        
                        if isinstance(fechas, (list, tuple)) and len(fechas) == 2:
                            fecha_ini, fecha_fin = fechas[0], fechas[1]
                            duracion_dias = (fecha_fin - fecha_ini).days + 1
                        else:
                            fecha_ini = fechas[0] if isinstance(fechas, (list, tuple)) else fechas
                            fecha_fin = fecha_ini
                            duracion_dias = 1
                            
                        st.info(f"📅 Duración total: **{duracion_dias} día(s)**")

                    if tipo_permiso == "Maternidad (Lactancia)":
                        st.caption("ℹ️ **Impacto:** Reduce la jornada laboral a 7 horas/día. Exenta de atrasos y salidas tempranas.")
                    else:
                        st.caption("ℹ️ **Impacto:** Durante el rango seleccionado los días **NO se tomarán como FALTA ni Atraso**.")

                    btn_guardar = st.form_submit_button("💾 Registrar y Aplicar Novedad")

                    if btn_guardar:
                        nueva_novedad = {
                            "ID_Novedad": f"NOV-{len(st.session_state['novedades_registradas']) + 1:03d}",
                            "Empleado": emp_seleccionado,
                            "Tipo_Novedad": tipo_permiso,
                            "Fecha_Inicio": str(fecha_ini),
                            "Fecha_Fin": str(fecha_fin),
                            "Duracion_Dias": duracion_dias,
                            "Registrado_Por": usuario_actual
                        }
                        
                        st.session_state['novedades_registradas'].append(nueva_novedad)
                        st.success(f"✅ Novedad registrada exitosamente para {emp_seleccionado} del {fecha_ini} al {fecha_fin}.")

        st.subheader("📋 Registro de Novedades Vigentes")
        df_mostrar = obtener_novedades_consolidadas()
        if df_mostrar is not None and not df_mostrar.empty:
            cols_vis = [c for c in df_mostrar.columns if not str(c).startswith('Unnamed')]
            st.dataframe(df_mostrar[cols_vis], use_container_width=True, hide_index=True)
        else:
            st.info("No hay novedades registradas hasta la fecha.")

# -----------------------------------------------------------------------------
# 5. APROBACIONES SUPERVISORES (🔒 CONTROLADO POR PIN Y SUPERVISOR)
# -----------------------------------------------------------------------------
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Centro de Aprobaciones y Excepciones")

    if not pin_ok:
        st.warning("🔒 Ingrese su PIN de 4 dígitos en la barra lateral para desbloquear el módulo de Aprobaciones.")
        st.stop()

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
        df_params = cargar_parametros()
        try:
            df_emp = load_sheet_data("01_Maestro_Empleados")
        except Exception:
            df_emp = None
        
        df_nov = obtener_novedades_consolidadas()

        df_res = process_attendance(df_bio, df_params, df_nov, df_emp)
        df_excepciones = detect_exceptions(df_res)
        df_canje_resumen = get_canje_summary(df_res)

        df_excepciones = filter_dataframe_by_supervisor(df_excepciones, 'Nombre', empleados_permitidos, rol_actual)
        df_canje_resumen = filter_dataframe_by_supervisor(df_canje_resumen, 'Nombre', empleados_permitidos, rol_actual)

    except Exception as e:
        df_excepciones = pd.DataFrame()
        df_canje_resumen = pd.DataFrame()
        st.warning(f"No se pudieron procesar las excepciones biométricas: {e}")

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
            df_params = cargar_parametros()
            try:
                df_emp = load_sheet_data("01_Maestro_Empleados")
            except Exception:
                df_emp = None
                
            df_nov = obtener_novedades_consolidadas()
                
            df_resultado = process_attendance(df_bio, df_params, df_nov, df_emp)

            if df_resultado is not None and not df_resultado.empty:
                col_filtro1, col_filtro2 = st.columns(2)
                
                with col_filtro1:
                    empleados = ["Todos"] + list(df_resultado['Nombre'].unique())
                    emp_sel = st.selectbox("Filtrar por Empleado:", empleados)
                
                with col_filtro2:
                    turnos = ["Todos", "Diurno", "Nocturno", "General"]
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
