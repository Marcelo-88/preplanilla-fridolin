import streamlit as st
import pandas as pd
import io
from datetime import datetime

from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions, get_canje_summary
from modules.auth_permissions import render_user_selector, filter_dataframe_by_supervisor
from modules.audit_logger import AuditLogger
from modules.lock_manager import LockManager
from modules.novedades import NovedadesManager
from modules.excel_exporter import ExcelExporter

# Inicialización de Gestores Persistence/DB
@st.cache_resource
def get_managers():
    audit = AuditLogger()
    lock = LockManager()
    nov = NovedadesManager()
    return audit, lock, nov

audit_log, lock_mgr, nov_mgr = get_managers()

# Caching de Carga de Hojas de Cálculo
@st.cache_data(ttl=300, show_spinner=False)
def cached_load_sheet_data(sheet_name):
    return load_sheet_data(sheet_name)

# Caching de Procesamiento de Asistencia
@st.cache_data(ttl=300, show_spinner=False)
def run_cached_attendance_processing(df_bio, df_params, df_emp, _nov_mgr):
    return process_attendance(df_bio, df_params, None, df_emp, _nov_mgr)

@st.cache_data(ttl=300, show_spinner=False)
def run_cached_exceptions(df_res):
    return detect_exceptions(df_res)

@st.cache_data(ttl=300, show_spinner=False)
def run_cached_canje(df_res):
    return get_canje_summary(df_res)


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
    df_emp_master = cached_load_sheet_data("01_Maestro_Empleados")
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
st.sidebar.caption("Sistema de Control de Asistencia v2.0")

# -----------------------------------------------------------------------------
# 1. PARÁMETROS Y REGLAS
# -----------------------------------------------------------------------------
if opcion == "📊 Parámetros y Reglas":
    st.header("Parámetros y Reglas del Sistema")
    try:
        df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
        st.dataframe(df_params, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 2. MAESTRO DE EMPLEADOS
# -----------------------------------------------------------------------------
elif opcion == "👥 Maestro de Empleados":
    st.header("Maestro de Empleados")
    try:
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        cols_sin_pin = [col for col in df_emp.columns if col.strip().upper() != "PIN"]
        df_emp_vista = df_emp[cols_sin_pin]
        st.dataframe(df_emp_vista, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 3. IMPORTACIÓN BIOMÉTRICO
# -----------------------------------------------------------------------------
elif opcion == "⏱️ Importación Biométrico":
    st.header("Registros del Biométrico")
    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        st.dataframe(df_bio, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error al cargar la pestaña: {e}")

# -----------------------------------------------------------------------------
# 4. NOVEDADES Y PERMISOS
# -----------------------------------------------------------------------------
elif opcion == "📝 Novedades y Permisos":
    st.header("Novedades, Licencias y Permisos Especiales")
    st.info("💡 Incluye licencias legales, bajas médicas, vacaciones y Reducción de Lactancia Maternidad (-1 hora diaria).")

    tab_ver_nov, tab_crear_nov = st.tabs(["📋 Novedades Registradas", "➕ Registrar Nueva Novedad"])

    with tab_ver_nov:
        try:
            df_nov_sheet = cached_load_sheet_data("04_Novedades_y_Permisos")
        except Exception:
            df_nov_sheet = pd.DataFrame()

        df_nov_local = pd.DataFrame(nov_mgr.obtener_todas_novedades())
        
        if not df_nov_local.empty and not df_nov_sheet.empty:
            df_nov_comb = pd.concat([df_nov_sheet, df_nov_local], ignore_index=True)
        elif not df_nov_local.empty:
            df_nov_comb = df_nov_local
        else:
            df_nov_comb = df_nov_sheet

        st.dataframe(df_nov_comb, use_container_width=True, hide_index=True)

    with tab_crear_nov:
        if not pin_ok:
            st.warning("🔒 Requiere ingresar su PIN de Supervisor en la barra lateral para registrar novedades.")
        else:
            st.subheader("Formulario de Registro de Novedad / Licencia")
            with st.form("form_nueva_novedad"):
                try:
                    df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                    df_emp.columns = [str(col).strip() for col in df_emp.columns]
                    col_nombre = 'Nombre_Completo' if 'Nombre_Completo' in df_emp.columns else ('Nombre' if 'Nombre' in df_emp.columns else None)
                    
                    if col_nombre:
                        df_emp_fil = filter_dataframe_by_supervisor(df_emp, col_nombre, empleados_permitidos, rol_actual)
                        lista_emps = df_emp_fil[col_nombre].dropna().unique().tolist()
                    else:
                        lista_emps = []
                except Exception:
                    lista_emps = []

                emp_seleccionado = st.selectbox("Seleccione Empleado:*", options=sorted(lista_emps))
                
                # Se utiliza directamente la propiedad de clase para omitir el objeto en caché
                tipo_nov = st.selectbox("Tipo de Novedad / Licencia:*", options=NovedadesManager.TIPOS_NOVEDAD)
                
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    fecha_ini = st.date_input("Fecha Inicio:*")
                with col_f2:
                    fecha_fin = st.date_input("Fecha Fin:*")
                
                justificacion_txt = st.text_area("Justificación / Certificado Médico / Observaciones:*")

                sub_nov = st.form_submit_button("✅ Guardar Novedad")
                if sub_nov:
                    if not emp_seleccionado or not justificacion_txt:
                        st.error("Debe completar todos los campos obligatorios.")
                    else:
                        emp_id = "EMP-000"
                        if col_nombre and col_nombre in df_emp.columns:
                            row_e = df_emp[df_emp[col_nombre] == emp_seleccionado]
                            if not row_e.empty:
                                col_id = 'Carnet_Identidad' if 'Carnet_Identidad' in df_emp.columns else ('ID' if 'ID' in df_emp.columns else None)
                                if col_id:
                                    emp_id = str(row_e[col_id].values[0])

                        res_reg = nov_mgr.registrar_novedad(
                            empleado_id=emp_id,
                            empleado_nombre=emp_seleccionado,
                            tipo_novedad=tipo_nov,
                            fecha_inicio=fecha_ini.strftime("%Y-%m-%d"),
                            fecha_fin=fecha_fin.strftime("%Y-%m-%d"),
                            justificacion=justificacion_txt,
                            registrado_por_pin=usuario_actual
                        )

                        if res_reg["exito"]:
                            audit_log.registrar_evento(
                                usuario_pin=usuario_actual,
                                usuario_nombre=usuario_actual,
                                accion="REGISTRO_NOVEDAD",
                                modulo="Novedades",
                                detalles={"empleado": emp_seleccionado, "tipo": tipo_nov, "inicio": str(fecha_ini), "fin": str(fecha_fin)}
                            )
                            st.cache_data.clear()
                            st.cache_resource.clear()
                            st.success(res_reg["mensaje"])
                            st.rerun()
                        else:
                            st.error(res_reg["mensaje"])

# -----------------------------------------------------------------------------
# 5. APROBACIONES SUPERVISORES
# -----------------------------------------------------------------------------
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Centro de Aprobaciones y Excepciones")

    if not pin_ok:
        st.warning("🔒 Ingrese su PIN de 4 dígitos en la barra lateral para desbloquear el módulo de Aprobaciones.")
        st.stop()

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos_disponibles = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True)
    except Exception:
        periodos_disponibles = [datetime.now().strftime('%Y-%m')]

    col_p1, col_p2 = st.columns([2, 2])
    with col_p1:
        periodo_sel = st.selectbox("🗓️ Seleccionar Período de Revisión:", options=periodos_disponibles)

    estado_periodo = lock_mgr.obtener_estado_periodo(periodo_sel)
    es_editable = lock_mgr.es_editable(periodo_sel, rol_actual)

    with col_p2:
        st.subheader(f"Estado Período: **{estado_periodo}**")
        if estado_periodo == "FINALIZADO" and not es_editable:
            st.error("🔒 Este período está CERRADO. Solo el Responsable de Operaciones puede desbloquearlo.")

    col_rev1, col_rev2, col_rev3 = st.columns(3)
    with col_rev1:
        if st.button("▶️ Marcar EN PROCESO"):
            res_c = lock_mgr.cambiar_estado(periodo_sel, lock_mgr.ESTADO_EN_PROCESO, usuario_actual, rol_actual)
            if res_c["exito"]:
                audit_log.registrar_evento(usuario_actual, usuario_actual, "CAMBIO_ESTADO_PERIODO", "Aprobaciones", {"periodo": periodo_sel, "nuevo_estado": "EN_PROCESO"})
                st.success(res_c["mensaje"])
                st.rerun()
            else:
                st.error(res_c["mensaje"])

    with col_rev2:
        if st.button("🔒 FINALIZAR y Cerrar Período"):
            res_c = lock_mgr.cambiar_estado(periodo_sel, lock_mgr.ESTADO_FINALIZADO, usuario_actual, rol_actual)
            if res_c["exito"]:
                audit_log.registrar_evento(usuario_actual, usuario_actual, "CAMBIO_ESTADO_PERIODO", "Aprobaciones", {"periodo": periodo_sel, "nuevo_estado": "FINALIZADO"})
                st.success(res_c["mensaje"])
                st.rerun()
            else:
                st.error(res_c["mensaje"])

    with col_rev3:
        if estado_periodo == "FINALIZADO" and (rol_actual == "Jefe de Producción"):
            if st.button("🔓 Desbloquear Período (Superusuario)"):
                res_c = lock_mgr.cambiar_estado(periodo_sel, lock_mgr.ESTADO_PENDIENTE, usuario_actual, rol_actual, motivo="Desbloqueo por Jefatura")
                if res_c["exito"]:
                    audit_log.registrar_evento(usuario_actual, usuario_actual, "DESBLOQUEO_PERIODO", "Aprobaciones", {"periodo": periodo_sel})
                    st.success(res_c["mensaje"])
                    st.rerun()

    st.divider()

    tab_excepciones, tab_canje_masivo, tab_regularizar = st.tabs([
        "🚨 Excepciones Automáticas", 
        "⚖️ Canje Masivo (Bolsa HE x Faltas)", 
        "➕ Regularizar Olvido Marcación"
    ])

    try:
        df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
        try:
            df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        except Exception:
            df_emp = None

        df_bio_periodo = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == periodo_sel].copy() if 'dt_temp' in df_bio.columns else df_bio

        # Procesamiento optimizado y cacheado
        df_res = run_cached_attendance_processing(df_bio_periodo, df_params, df_emp, nov_mgr)
        df_excepciones = run_cached_exceptions(df_res)
        df_canje_resumen = run_cached_canje(df_res)

        df_excepciones = filter_dataframe_by_supervisor(df_excepciones, 'Nombre', empleados_permitidos, rol_actual)
        df_canje_resumen = filter_dataframe_by_supervisor(df_canje_resumen, 'Nombre', empleados_permitidos, rol_actual)

    except Exception as e:
        df_excepciones = pd.DataFrame()
        df_canje_resumen = pd.DataFrame()
        st.warning(f"No se pudieron procesar las excepciones para el período {periodo_sel}: {e}")

    # TAB 1: EXCEPCIONES AUTOMÁTICAS
    with tab_excepciones:
        if df_excepciones is not None and not df_excepciones.empty:
            st.subheader(f"Excepciones Detectadas ({periodo_sel})")

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
            m3.metric("Sol. Horas Extras / Dom", len(df_fil_exc[df_fil_exc['Tipo Excepción'].str.contains('Horas Extras')]))
            m4.metric("Desfases Ingreso", len(df_fil_exc[df_fil_exc['Tipo Excepción'] == 'Desfase Horario Ingreso']))

            df_edited_exc = st.data_editor(
                df_fil_exc,
                use_container_width=True,
                hide_index=True,
                disabled=["ID", "Nombre", "Fecha", "Tipo Excepción", "Detalle Excepción", "Valor a Revisar"] if not es_editable else [],
                column_config={
                    "Decisión Supervisor": st.column_config.SelectboxColumn(
                        "Decisión",
                        options=["Pendiente", "Aprobado (Pago)", "Acumular (Próx. Mes)", "Rechazado", "Justificado", "Canjeado"],
                        required=True
                    ),
                    "Tipo Falta": st.column_config.SelectboxColumn(
                        "Tipo Falta (Para Contabilidad)",
                        options=["N/A", "Justificada", "Injustificada"],
                        required=True
                    ),
                    "Observaciones": st.column_config.TextColumn("Observaciones / Motivo", width="medium")
                }
            )

            st.divider()
            st.subheader("📥 Exportación Profesional a Excel")
            
            archivo_path = f"Aprobaciones_{periodo_sel}.xlsx"
            ExcelExporter.exportar_aprobaciones(df_edited_exc.to_dict('records'), periodo_sel, archivo_path)
            
            with open(archivo_path, "rb") as f:
                st.download_button(
                    label="📥 Descargar Aprobaciones Procesadas (Excel)",
                    data=f,
                    file_name=f"Aprobaciones_Supervisores_{periodo_sel}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.success("🎉 No se detectaron excepciones pendientes para el personal asignado en este período.")

    # TAB 2: CANJE MASIVO
    with tab_canje_masivo:
        st.subheader("⚖️ Canje Masivo de Horas Extras por Faltas")
        if df_canje_resumen is not None and not df_canje_resumen.empty:
            df_edited_canje = st.data_editor(
                df_canje_resumen,
                use_container_width=True,
                hide_index=True,
                disabled=[] if es_editable else ["Días a Canjear (Aplicar)", "Estado Canje"],
                column_config={
                    "ID": st.column_config.Column(disabled=True),
                    "Nombre": st.column_config.Column(disabled=True),
                    "Turno Dominante": st.column_config.Column(disabled=True),
                    "Horas Costo por Día": st.column_config.NumberColumn("Costo Día (hrs)", disabled=True, format="%.0f hrs"),
                    "Bolsa HE Acumulada (hrs)": st.column_config.NumberColumn("Bolsa HE (hrs)", disabled=True, format="%.2f hrs"),
                    "Días Máx. Canjeables": st.column_config.NumberColumn("Días Máx.", disabled=True, format="%d días"),
                    "Faltas Registradas": st.column_config.NumberColumn("Faltas Reg.", disabled=True, format="%d días"),
                    "Días a Canjear (Aplicar)": st.column_config.NumberColumn("Días a Canjear", min_value=0, max_value=10, step=1),
                    "Estado Canje": st.column_config.SelectboxColumn("Estado Canje", options=["Sin Aplicar", "Canje Aplicado", "Rechazado por Supervisor"], required=True)
                }
            )

            dias_totales_canjeados = df_edited_canje['Días a Canjear (Aplicar)'].sum()
            c_m1, c_m2 = st.columns(2)
            c_m1.metric("Personal con Bolsa HE / Faltas", len(df_edited_canje))
            c_m2.metric("Total Días Canjeados", f"{int(dias_totales_canjeados)} días")
        else:
            st.info("No hay empleados a su cargo con saldo de horas extras o faltas en este período.")

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
                elif not es_editable:
                    st.error("No se pueden registrar regularizaciones en un período CERRADO.")
                else:
                    audit_log.registrar_evento(
                        usuario_pin=usuario_actual,
                        usuario_nombre=usuario_actual,
                        accion="REGULARIZACION_OMISION",
                        modulo="Aprobaciones",
                        detalles={"empleado": nombre_emp_reg, "fecha": str(fecha_reg), "tipo": tipo_marcacion, "motivo": motivo_reg}
                    )
                    st.success(f"Regularización registrada para {nombre_emp_reg} el día {fecha_reg}.")

# -----------------------------------------------------------------------------
# 6. PRE-PLANILLA Y REPORTES
# -----------------------------------------------------------------------------
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("Reporte Consolidado de Asistencia para RRHH / Contabilidad")
    
    with st.spinner("Procesando marcaciones, novedades y tiempos..."):
        try:
            df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
            df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
            df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                
            df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
            periodos_rep = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True)
            
            p_sel_rep = st.selectbox("🗓️ Filtrar Período de Reporte:", options=["Todos"] + periodos_rep)

            if p_sel_rep != "Todos":
                df_bio_rep = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == p_sel_rep].copy()
            else:
                df_bio_rep = df_bio

            # Procesamiento optimizado y cacheado
            df_resultado = run_cached_attendance_processing(df_bio_rep, df_params, df_emp, nov_mgr)

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
                
                archivo_rep = f"PrePlanilla_{p_sel_rep}.xlsx"
                ExcelExporter.exportar_preplanilla(df_filtrado.to_dict('records'), p_sel_rep, archivo_rep)

                with open(archivo_rep, "rb") as f:
                    st.download_button(
                        label="📥 Descargar Reporte Consolidado (Excel)",
                        data=f,
                        file_name=f"Reporte_PrePlanilla_Fridolin_{p_sel_rep}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        except Exception as e:
            st.error(f"Error durante el procesamiento del reporte: {e}")
