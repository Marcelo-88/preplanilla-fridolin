import streamlit as st
import pandas as pd
import io
from datetime import datetime

from modules.data_loader import load_sheet_data, clean_ci_str
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

# Cargar Maestro de Empleados para autenticación
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
    st.info("💡 Vinculación mediante Carnet de Identidad. Incluye licencias, vacaciones, cambios de turno con horario dinámico y Reducción de Lactancia.")

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
            
            try:
                df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                df_emp_fil = filter_dataframe_by_supervisor(df_emp, 'Carnet_Identidad', empleados_permitidos, rol_actual)
                
                dict_opciones_emp = {}
                for _, r in df_emp_fil.iterrows():
                    ci = clean_ci_str(r.get('Carnet_Identidad', ''))
                    nom = str(r.get('Nombre_Completo', r.get('Nombre', ''))).strip()
                    if ci and nom:
                        dict_opciones_emp[f"{nom} - (CI: {ci})"] = (ci, nom)
            except Exception:
                dict_opciones_emp = {}

            with st.form("form_nueva_novedad"):
                label_emp = st.selectbox("Seleccione Empleado (Nombre - CI):*", options=sorted(dict_opciones_emp.keys()))
                tipo_nov = st.selectbox("Tipo de Novedad / Licencia:*", options=NovedadesManager.TIPOS_NOVEDAD)
                
                hora_in_proyectada = None
                hora_out_proyectada = None
                if "CAMBIO_TURNO" in tipo_nov:
                    st.markdown("---")
                    st.caption("🕒 Horario Proyectado para el Cambio de Turno (Opcional):")
                    c_h1, c_h2 = st.columns(2)
                    with c_h1:
                        h_in = st.time_input("Hora Entrada Proyectada:", value=datetime.strptime("07:30", "%H:%M").time())
                        hora_in_proyectada = h_in.strftime("%H:%M")
                    with c_h2:
                        h_out = st.time_input("Hora Salida Proyectada:", value=datetime.strptime("15:30", "%H:%M").time())
                        hora_out_proyectada = h_out.strftime("%H:%M")
                    st.markdown("---")

                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    fecha_ini = st.date_input("Fecha Inicio:*")
                with col_f2:
                    fecha_fin = st.date_input("Fecha Fin:*")
                
                justificacion_txt = st.text_area("Justificación / Certificado Médico / Observaciones:*")

                sub_nov = st.form_submit_button("✅ Guardar Novedad")
                if sub_nov:
                    if not label_emp or not justificacion_txt:
                        st.error("Debe completar todos los campos obligatorios.")
                    else:
                        ci_sel, nom_sel = dict_opciones_emp[label_emp]

                        res_reg = nov_mgr.registrar_novedad(
                            carnet_identidad=ci_sel,
                            empleado_nombre=nom_sel,
                            tipo_novedad=tipo_nov,
                            fecha_inicio=fecha_ini.strftime("%Y-%m-%d"),
                            fecha_fin=fecha_fin.strftime("%Y-%m-%d"),
                            justificacion=justificacion_txt,
                            registrado_por_pin=usuario_actual,
                            hora_entrada_proyectada=hora_in_proyectada,
                            hora_salida_proyectada=hora_out_proyectada
                        )

                        if res_reg["exito"]:
                            audit_log.registrar_evento(
                                usuario_pin=usuario_actual,
                                usuario_nombre=usuario_actual,
                                accion="REGISTRO_NOVEDAD",
                                modulo="Novedades",
                                detalles={"ci": ci_sel, "empleado": nom_sel, "tipo": tipo_nov, "inicio": str(fecha_ini), "fin": str(fecha_fin)}
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
    es_superusuario = ("Acceso Total" in rol_actual or rol_actual in LockManager.ROLES_SUPERUSUARIO)
    es_editable = lock_mgr.es_editable(periodo_sel, rol_actual)

    with col_p2:
        st.subheader(f"Estado Período: **{estado_periodo}**")
        if estado_periodo == "FINALIZADO" and not es_superusuario:
            st.error("🔒 Este período está CERRADO. Contacte al Responsable de Operaciones para reaperturas.")

    col_rev1, col_rev2, col_rev3 = st.columns(3)
    with col_rev1:
        if st.button("▶️ INICIAR APROBACIONES"):
            res_c = lock_mgr.cambiar_estado(periodo_sel, lock_mgr.ESTADO_EN_PROCESO, usuario_actual, rol_actual)
            if res_c["exito"]:
                audit_log.registrar_evento(usuario_actual, usuario_actual, "CAMBIO_ESTADO_PERIODO", "Aprobaciones", {"periodo": periodo_sel, "nuevo_estado": lock_mgr.ESTADO_EN_PROCESO})
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
        if estado_periodo == "FINALIZADO" and es_superusuario:
            if st.button("🔓 Desbloquear Período Global"):
                res_c = lock_mgr.cambiar_estado(periodo_sel, lock_mgr.ESTADO_PENDIENTE, usuario_actual, rol_actual, motivo="Desbloqueo Global")
                if res_c["exito"]:
                    audit_log.registrar_evento(usuario_actual, usuario_actual, "DESBLOQUEO_PERIODO", "Aprobaciones", {"periodo": periodo_sel})
                    st.success(res_c["mensaje"])
                    st.rerun()

    # --- REVERSIÓN INDIVIDUAL PARA ACCESO TOTAL (Ever Medrano) ---
    if es_superusuario:
        with st.expander("🛠️ Panel de Reversión / Desbloqueo Individual por Colaborador (Exclusivo Acceso Total)"):
            c_rev_ci, c_rev_mot, c_rev_btn = st.columns([2, 3, 2])
            with c_rev_ci:
                try:
                    df_emp_tot = cached_load_sheet_data("01_Maestro_Empleados")
                    dict_rev = {f"{r.get('Nombre_Completo', r.get('Nombre'))} (CI: {clean_ci_str(r.get('Carnet_Identidad'))})": clean_ci_str(r.get('Carnet_Identidad')) for _, r in df_emp_tot.iterrows()}
                    emp_rev_sel = st.selectbox("Seleccionar Empleado a Revertir:", options=sorted(dict_rev.keys()))
                    ci_rev_target = dict_rev.get(emp_rev_sel)
                except Exception:
                    ci_rev_target = st.text_input("CI de Colaborador a Revertir:")
            with c_rev_mot:
                motivo_rev = st.text_input("Motivo de la Reversión Individual:", placeholder="Ej: Error en registro de horas por el supervisor")
            with c_rev_btn:
                st.write("")
                st.write("")
                if st.button("🔄 Revertir Decisiones / Reabrir Empleado"):
                    if ci_rev_target:
                        res_r = lock_mgr.cambiar_estado_empleado(periodo_sel, ci_rev_target, lock_mgr.ESTADO_PENDIENTE, usuario_actual, motivo=motivo_rev)
                        st.success(f"Se reabrió el período individualmente para CI: {ci_rev_target}")
                        st.rerun()

    st.divider()

    tab_excepciones, tab_canje_masivo, tab_regularizar = st.tabs([
        "🚨 Excepciones Automáticas (UX optimizada)", 
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

        df_res = run_cached_attendance_processing(df_bio_periodo, df_params, df_emp, nov_mgr)
        df_excepciones = run_cached_exceptions(df_res)
        df_canje_resumen = run_cached_canje(df_res)

        df_excepciones = filter_dataframe_by_supervisor(df_excepciones, 'Carnet_Identidad', empleados_permitidos, rol_actual)
        df_canje_resumen = filter_dataframe_by_supervisor(df_canje_resumen, 'Carnet_Identidad', empleados_permitidos, rol_actual)

        # Cargar decisiones previas guardadas en SQLite
        decisiones_previas = lock_mgr.obtener_decisiones_excepciones(periodo_sel)
        if df_excepciones is not None and not df_excepciones.empty:
            for idx, r in df_excepciones.iterrows():
                key = (clean_ci_str(r['Carnet_Identidad']), str(r['Fecha']), str(r['Tipo Excepción']))
                if key in decisiones_previas:
                    df_excepciones.at[idx, 'Decisión Supervisor'] = decisiones_previas[key]['decision']
                    df_excepciones.at[idx, 'Tipo Falta'] = decisiones_previas[key]['tipo_falta']
                    df_excepciones.at[idx, 'Observaciones'] = decisiones_previas[key]['observaciones']

    except Exception as e:
        df_excepciones = pd.DataFrame()
        df_canje_resumen = pd.DataFrame()
        st.warning(f"No se pudieron procesar las excepciones para el período {periodo_sel}: {e}")

    # TAB 1: EXCEPCIONES AUTOMÁTICAS
    with tab_excepciones:
        if df_excepciones is not None and not df_excepciones.empty:
            st.subheader(f"Resumen Ejecutivo de Excepciones ({periodo_sel})")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Excepciones", len(df_excepciones))
            m2.metric("Faltas / Omisiones", len(df_excepciones[df_excepciones['Tipo Excepción'] == 'Falta / Omisión Marcación']))
            m3.metric("Horas Extras / Domingo", len(df_excepciones[df_excepciones['Tipo Excepción'].str.contains('Horas Extras')]))
            m4.metric("Desfases Horario", len(df_excepciones[df_excepciones['Tipo Excepción'] == 'Desfase Horario Ingreso']))

            st.markdown("---")
            
            # --- BUSCADOR POR COLABORADOR ---
            c_busq1, c_busq2 = st.columns([3, 1])
            with c_busq1:
                filtro_persona_exc = st.text_input("🔍 Buscar colaborador por Nombre o CI (Excepciones):", placeholder="Ej: Lynn Soria o 8228265")
            
            df_exc_vista = df_excepciones.copy()
            if filtro_persona_exc:
                q = filtro_persona_exc.lower().strip()
                df_exc_vista = df_exc_vista[
                    df_exc_vista['Nombre'].str.lower().str.contains(q) | 
                    df_exc_vista['Carnet_Identidad'].str.contains(q)
                ]

            st.caption("Seleccione un colaborador para revisar y tomar decisiones por tarjeta:")

            grupos_emp = df_exc_vista.groupby(['Carnet_Identidad', 'Nombre'])
            registros_editados_totales = []

            for (ci_k, nom_k), grp_emp in grupos_emp:
                cant_exc = len(grp_emp)
                emp_editable = lock_mgr.es_editable(periodo_sel, rol_actual, ci_k)
                
                with st.expander(f"👤 **{nom_k}** — CI: `{ci_k}` ({cant_exc} excepción(es) pendiente(s))", expanded=False):
                    df_edit_sub = st.data_editor(
                        grp_emp,
                        use_container_width=True,
                        hide_index=True,
                        disabled=["Carnet_Identidad", "Nombre", "Fecha", "Tipo Excepción", "Detalle Excepción", "Valor a Revisar"] if not emp_editable else [],
                        column_config={
                            "Carnet_Identidad": st.column_config.Column("CI", disabled=True),
                            "Decisión Supervisor": st.column_config.SelectboxColumn(
                                "Decisión",
                                options=["Pendiente", "Aprobado (Pago)", "Acumular (Próx. Mes)", "Rechazado", "Justificado", "Canjeado"],
                                required=True
                            ),
                            "Tipo Falta": st.column_config.SelectboxColumn(
                                "Tipo Falta",
                                options=["N/A", "Justificada", "Injustificada"],
                                required=True
                            ),
                            "Observaciones": st.column_config.TextColumn("Observaciones / Motivo", width="medium")
                        },
                        key=f"editor_exc_{ci_k}"
                    )
                    registros_editados_totales.extend(df_edit_sub.to_dict('records'))

            if st.button("💾 Guardar Decisiones de Excepciones", type="primary"):
                if registros_editados_totales:
                    lock_mgr.guardar_decisiones_excepciones(periodo_sel, registros_editados_totales, usuario_actual)
                    st.cache_data.clear()
                    st.success("✅ Decisiones guardadas correctamente en la base de datos.")
                    st.rerun()

            st.divider()
            st.subheader("📥 Exportación Consolidada")
            
            archivo_path = f"Aprobaciones_{periodo_sel}.xlsx"
            ExcelExporter.exportar_aprobaciones(
                df_excepciones.to_dict('records'), 
                df_canje_resumen.to_dict('records') if df_canje_resumen is not None else [], 
                periodo_sel, 
                archivo_path
            )
            
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
            
            # --- BUSCADOR EN CANJE ---
            filtro_persona_canje = st.text_input("🔍 Buscar colaborador por Nombre o CI (Canje):", placeholder="Ej: Ever Medrano")
            df_canje_vista = df_canje_resumen.copy()
            if filtro_persona_canje:
                q_c = filtro_persona_canje.lower().strip()
                df_canje_vista = df_canje_vista[
                    df_canje_vista['Nombre'].str.lower().str.contains(q_c) | 
                    df_canje_vista['Carnet_Identidad'].str.contains(q_c)
                ]

            df_edited_canje = st.data_editor(
                df_canje_vista,
                use_container_width=True,
                hide_index=True,
                disabled=[] if es_editable else ["Días a Canjear (Aplicar)", "Estado Canje"],
                column_config={
                    "Carnet_Identidad": st.column_config.Column("CI", disabled=True),
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
                id_emp_reg = st.text_input("Carnet de Identidad (CI):*")
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
                        detalles={"ci": clean_ci_str(id_emp_reg), "empleado": nombre_emp_reg, "fecha": str(fecha_reg), "tipo": tipo_marcacion, "motivo": motivo_reg}
                    )
                    st.success(f"Regularización registrada para {nombre_emp_reg} (CI: {id_emp_reg}) el día {fecha_reg}.")

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

            df_resultado = run_cached_attendance_processing(df_bio_rep, df_params, df_emp, nov_mgr)

            # Impactar decisiones de excepciones en el DataFrame final
            if df_resultado is not None and not df_resultado.empty and p_sel_rep != "Todos":
                decisiones_guardadas = lock_mgr.obtener_decisiones_excepciones(p_sel_rep)
                for idx, row in df_resultado.iterrows():
                    ci_row = clean_ci_str(row['Carnet_Identidad'])
                    f_row = str(row['Fecha'])
                    
                    # Verificar si existe alguna decisión para este colaborador en esta fecha
                    for (d_ci, d_f, d_tipo), d_val in decisiones_guardadas.items():
                        if d_ci == ci_row and d_f == f_row:
                            dec = d_val['decision']
                            if dec == "Justificado":
                                df_resultado.at[idx, 'Falta Justificada'] = 1
                                df_resultado.at[idx, 'Falta Injustificada'] = 0
                                df_resultado.at[idx, 'Estado'] = 'Justificado por Supervisor'
                            elif dec == "Rechazado":
                                df_resultado.at[idx, 'Horas Extras'] = 0.0
                                df_resultado.at[idx, 'Estado'] = 'Rechazado por Supervisor'

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
