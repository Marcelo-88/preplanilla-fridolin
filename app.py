import streamlit as st
import pandas as pd
import io
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

# --- IMPORTS DE MÓDULOS DEL PROYECTO ---
from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions, get_canje_summary
from modules.auth_permissions import render_user_selector, filter_dataframe_by_supervisor
from modules.excel_exporter import ExcelExporter

# Importamos los managers nuevos (Supabase)
from modules.audit_logger import AuditLogger
from modules.lock_manager import LockManager
from modules.novedades import NovedadesManager

try:
    from modules.tarifas_manager import (
        cargar_tarifas, guardar_tarifas, actualizar_excepcion_empleado, eliminar_excepcion_empleado,
        obtener_config_periodo, guardar_config_periodo, clean_ci
    )
except ImportError:
    def clean_ci(val):
        if val is None:
            return ""
        return str(val).split('.')[0].strip().upper()

# -----------------------------------------------------------------------------
# GESTOR PERSISTENTE DE TARIFAS Y EXCEPCIONES (DISCO / JSON) - Se mantiene por ahora
# -----------------------------------------------------------------------------
TARIFAS_JSON_PATH = "tarifas_config.json"

def cargar_todas_tarifas_json() -> dict:
    if os.path.exists(TARIFAS_JSON_PATH):
        try:
            with open(TARIFAS_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_todas_tarifas_json(data: dict) -> bool:
    try:
        with open(TARIFAS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error guardando tarifas en JSON: {e}")
        return False

def obtener_config_periodo_persistent(periodo: str) -> dict:
    all_data = cargar_todas_tarifas_json()
    if periodo in all_data:
        return all_data[periodo]
    
    try:
        from modules.tarifas_manager import obtener_config_periodo as orig_obtener
        cfg = orig_obtener(periodo)
        if cfg and isinstance(cfg, dict):
            all_data[periodo] = cfg
            guardar_todas_tarifas_json(all_data)
            return cfg
    except Exception:
        pass

    default_cfg = {
        "tarifas_base": {
            "diurno_normal": 100.0,
            "diurno_1_5": 150.0,
            "nocturno_normal": 120.0,
            "nocturno_1_5": 180.0
        },
        "excepciones": {}
    }
    all_data[periodo] = default_cfg
    guardar_todas_tarifas_json(all_data)
    return default_cfg

def guardar_config_periodo_persistent(periodo: str, config: dict) -> bool:
    all_data = cargar_todas_tarifas_json()
    all_data[periodo] = config
    res = guardar_todas_tarifas_json(all_data)
    try:
        from modules.tarifas_manager import guardar_config_periodo as orig_guardar
        orig_guardar(periodo, config)
    except Exception:
        pass
    return res

def actualizar_excepcion_empleado_persistent(ci: str, tipo_turno: str, monto: float, periodo: str) -> bool:
    config = obtener_config_periodo_persistent(periodo)
    ci_clean = clean_ci(ci)
    if "excepciones" not in config:
        config["excepciones"] = {}
    if ci_clean not in config["excepciones"]:
        config["excepciones"][ci_clean] = {}
    
    config["excepciones"][ci_clean][tipo_turno] = float(monto)
    res = guardar_config_periodo_persistent(periodo, config)
    try:
        from modules.tarifas_manager import actualizar_excepcion_empleado as orig_act
        orig_act(ci, tipo_turno, monto, periodo=periodo)
    except Exception:
        pass
    return res

def eliminar_excepcion_empleado_persistent(ci: str, periodo: str) -> bool:
    config = obtener_config_periodo_persistent(periodo)
    ci_clean = clean_ci(ci)
    if "excepciones" in config and ci_clean in config["excepciones"]:
        del config["excepciones"][ci_clean]
        res = guardar_config_periodo_persistent(periodo, config)
        try:
            from modules.tarifas_manager import eliminar_excepcion_empleado as orig_del
            orig_del(ci, periodo=periodo)
        except Exception:
            pass
        return res
    return False


# --- INICIALIZACIÓN DE GESTORES (Ahora usan Supabase) ---
@st.cache_resource
def get_managers():
    audit = AuditLogger()
    lock = LockManager()
    nov = NovedadesManager()
    return audit, lock, nov

audit_log, lock_mgr, nov_mgr = get_managers()


# Caching de Funciones de Datos
@st.cache_data(ttl=300, show_spinner=False)
def cached_load_sheet_data(sheet_name):
    return load_sheet_data(sheet_name)

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

# Autenticación y Credenciales
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
        "⏱️ Importación Biométrico",
        "📝 Novedades y Permisos",
        "✅ Aprobaciones Supervisores",
        "💵 Valores Monetizados",
        "📑 Pre-Planilla y Reportes",
        "📜 Bitácora de Auditoría"
    ]
)

st.sidebar.divider()
st.sidebar.caption("Sistema de Control de Asistencia v2.5")

# -----------------------------------------------------------------------------
# 1. PARÁMETROS Y REGLAS
# -----------------------------------------------------------------------------
if opcion == "📊 Parámetros y Reglas":
    st.header("⚙️ Parámetros y Reglas del Sistema")

    st.subheader("📋 Matriz de Parámetros Normativos")
    
    data_reglas = [
        {"Parámetro / Regla": "Tolerancia_Atraso_Min", "Valor": "10 min", "Descripción y Aplicación": "Regla 'Todo o Nada': Atrasos <= 10 min no se descuentan. Atrasos >= 11 min cobran el total acumulado desde el minuto 1."},
        {"Parámetro / Regla": "Tiempo_Comida_Min", "Valor": "30 min", "Descripción y Aplicación": "Descuento automático obligatorio de 0.5 horas en toda jornada con marcación de salida."},
        {"Parámetro / Regla": "Ventana_Pareo_Horas", "Valor": "18 hrs", "Descripción y Aplicación": "Ventana máxima continua para emparejar Entrada y Salida. Toda la jornada se asigna al Día de la Entrada."},
        {"Parámetro / Regla": "Jornada_Diurna_Base", "Valor": "8.0 hrs", "Descripción y Aplicación": "Horario oficial 07:00 a 15:30 (8.5h brutas - 0.5h comida) = 1.0 Turno."},
        {"Parámetro / Regla": "Jornada_Nocturna_Base", "Valor": "7.0 hrs", "Descripción y Aplicación": "Horario oficial 22:00 a 05:30 (7.5h brutas - 0.5h cena) = 1.0 Turno."},
        {"Parámetro / Regla": "Jornada_Nocturna_Especial", "Valor": "11.0 hrs", "Descripción y Aplicación": "Viernes y Domingos (Ingreso 16:00 a 19:30, Oficial 18:00 a 05:30) = 1.5 Turnos."},
        {"Parámetro / Regla": "Umbral_Excepción_Horario", "Valor": "30 min", "Descripción y Aplicación": "Entradas/Salidas anticipadas o tardías >= 30 min generan Excepción Pendiente. Por defecto se truncan al horario oficial."},
        {"Parámetro / Regla": "Alerta_7mo_Dia", "Valor": "7 días", "Descripción y Aplicación": "Genera alerta automática si un trabajador registra marcaciones los 7 días de una misma semana."},
    ]
    
    st.dataframe(pd.DataFrame(data_reglas), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 2. IMPORTACIÓN BIOMÉTRICO
# -----------------------------------------------------------------------------
elif opcion == "⏱️ Importación Biométrico":
    st.header("⏱️ Importación y Visualización de Marcaciones Biométricas")
    st.info("Esta sección carga los datos desde el Google Sheet configurado. Los datos se procesan en tiempo real.")

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        if df_bio is not None and not df_bio.empty:
            st.success(f"✅ Se cargaron {len(df_bio)} registros biométricos.")
            st.dataframe(df_bio.head(100), use_container_width=True)
        else:
            st.warning("No se encontraron datos en la hoja de biométrico.")
    except Exception as e:
        st.error(f"Error cargando biométrico: {e}")

# -----------------------------------------------------------------------------
# 3. NOVEDADES Y PERMISOS  (CORREGIDO - Lista desplegable)
# -----------------------------------------------------------------------------
elif opcion == "📝 Novedades y Permisos":
    st.header("📝 Gestión de Novedades, Permisos y Licencias")

    # Crear diccionario Nombre → CI del personal asignado
    dict_nombre_ci = {}
    try:
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        cols = {str(c).strip().lower(): c for c in df_emp.columns}
        c_nombre = next((cols[k] for k in cols if 'nombre' in k), None)
        c_ci = next((cols[k] for k in cols if any(x in k for x in ['carnet', 'ci', 'id'])), None)

        if c_nombre and c_ci:
            # Solo personal asignado al supervisor (o todos si es jefe)
            if empleados_permitidos:
                df_filtrado = df_emp[df_emp[c_nombre].astype(str).str.strip().isin(empleados_permitidos)]
            else:
                df_filtrado = df_emp

            for _, row in df_filtrado.iterrows():
                nom = str(row[c_nombre]).strip()
                ci = clean_ci(row[c_ci])
                if nom and ci:
                    dict_nombre_ci[nom] = ci
    except Exception as e:
        st.warning(f"No se pudo cargar lista de personal: {e}")

    with st.form("form_novedad"):
        col1, col2 = st.columns(2)
        with col1:
            if dict_nombre_ci:
                emp_nombre = st.selectbox("Nombre Completo*", options=sorted(dict_nombre_ci.keys()))
                emp_id = dict_nombre_ci.get(emp_nombre, "")
                st.text_input("CI / Carnet del Empleado*", value=emp_id, disabled=True)
            else:
                emp_id = st.text_input("CI / Carnet del Empleado*")
                emp_nombre = st.text_input("Nombre Completo*")

            tipo_nov = st.selectbox("Tipo de Novedad*", nov_mgr.obtener_tipos_novedad())
        with col2:
            f_ini = st.date_input("Fecha Inicio*")
            f_fin = st.date_input("Fecha Fin*")
            justificacion = st.text_area("Justificación / Observación")

        submitted = st.form_submit_button("💾 Registrar Novedad")
        if submitted:
            if not emp_id or not emp_nombre:
                st.warning("Complete los campos obligatorios.")
            else:
                resultado = nov_mgr.registrar_novedad(
                    empleado_id=emp_id,
                    empleado_nombre=emp_nombre,
                    tipo_novedad=tipo_nov,
                    fecha_inicio=str(f_ini),
                    fecha_fin=str(f_fin),
                    justificacion=justificacion,
                    registrado_por_pin=usuario_actual
                )
                if resultado.get("exito"):
                    st.success(resultado.get("mensaje"))
                    audit_log.registrar_evento(
                        usuario_pin=usuario_actual,
                        usuario_nombre=usuario_actual,
                        accion="REGISTRAR_NOVEDAD",
                        modulo="Novedades",
                        detalles={"empleado": emp_nombre, "tipo": tipo_nov, "desde": str(f_ini), "hasta": str(f_fin)}
                    )
                else:
                    st.error(resultado.get("mensaje"))

    st.divider()
    st.subheader("📋 Novedades Registradas")
    todas = nov_mgr.obtener_todas_novedades()
    if todas:
        st.dataframe(pd.DataFrame(todas), use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay novedades registradas.")

# -----------------------------------------------------------------------------
# 4. APROBACIONES SUPERVISORES
# -----------------------------------------------------------------------------
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Panel de Aprobaciones de Supervisores")

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")

        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True)
        
        if not periodos:
            periodos = [datetime.now().strftime('%Y-%m')]

        periodo_sel = st.selectbox("🗓️ Seleccionar Período:", periodos)

        # Estado del período
        estado_actual = lock_mgr.obtener_estado_periodo(periodo_sel, usuario=usuario_actual)
        es_editable = lock_mgr.es_editable(periodo_sel, rol_actual, usuario=usuario_actual)

        col_est1, col_est2, col_est3 = st.columns([2, 2, 3])
        col_est1.metric("Estado Actual", estado_actual)

        with col_est2:
            if st.button("▶️ Marcar EN PROCESO"):
                res = lock_mgr.cambiar_estado(periodo_sel, "EN_PROCESO", usuario_actual, rol_actual, usuario_actual)
                if res["exito"]:
                    st.success(res["mensaje"])
                    st.rerun()
                else:
                    st.error(res["mensaje"])

        with col_est3:
            if st.button("🔒 FINALIZAR Período", type="primary"):
                res = lock_mgr.cambiar_estado(periodo_sel, "FINALIZADO", usuario_actual, rol_actual, usuario_actual)
                if res["exito"]:
                    audit_log.registrar_evento(usuario_actual, usuario_actual, "FINALIZAR_PERIODO", "Aprobaciones", {"periodo": periodo_sel})
                    st.success(res["mensaje"])
                    st.rerun()
                else:
                    st.error(res["mensaje"])

        # Procesamiento
        df_bio_periodo = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == periodo_sel].copy()
        df_resultado = run_cached_attendance_processing(df_bio_periodo, df_params, df_emp, nov_mgr)
        df_excepciones = run_cached_exceptions(df_resultado)
        df_canje_resumen = run_cached_canje(df_resultado)

        # Filtrar por supervisor si aplica
        if empleados_permitidos:
            df_resultado = filter_dataframe_by_supervisor(df_resultado, empleados_permitidos)
            if not df_excepciones.empty:
                df_excepciones = filter_dataframe_by_supervisor(df_excepciones, empleados_permitidos)
            if df_canje_resumen is not None and not df_canje_resumen.empty:
                df_canje_resumen = filter_dataframe_by_supervisor(df_canje_resumen, empleados_permitidos)

        tab_exc, tab_canje_masivo, tab_regularizar = st.tabs(["📋 Excepciones", "⚖️ Canje Masivo", "🛠️ Regularización"])

        # TAB 1: EXCEPCIONES
        with tab_exc:
            st.subheader(f"Excepciones Detectadas ({periodo_sel})")

            if not es_editable:
                st.info("🔒 **Edición Bloqueada:** Para habilitar la modificación de decisiones, presione el botón **'▶️ Marcar EN PROCESO'** arriba.")

            if not df_excepciones.empty:
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
                m3.metric("Sol. Horas Extras / Dom", len(df_fil_exc[df_fil_exc['Tipo Excepción'].str.contains('Horas Extras', na=False)]))
                m4.metric("Desfases Ingreso", len(df_fil_exc[df_fil_exc['Tipo Excepción'] == 'Desfase Horario Ingreso']))

                if not es_editable:
                    cols_deshabilitadas_exc = list(df_fil_exc.columns)
                else:
                    cols_deshabilitadas_exc = [c for c in ["Carnet_Identidad", "ID", "Nombre", "Fecha", "Tipo Excepción", "Detalle Excepción", "Valor a Revisar"] if c in df_fil_exc.columns]

                df_edited_exc = st.data_editor(
                    df_fil_exc,
                    use_container_width=True,
                    hide_index=True,
                    disabled=cols_deshabilitadas_exc,
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
                
                archivo_path = f"Aprobaciones_{periodo_sel}_{usuario_actual}.xlsx"
                ExcelExporter.exportar_aprobaciones(df_edited_exc.to_dict('records'), periodo_sel, archivo_path)
                
                with open(archivo_path, "rb") as f:
                    st.download_button(
                        label="📥 Descargar Aprobaciones Procesadas (Excel)",
                        data=f,
                        file_name=f"Aprobaciones_Supervisores_{periodo_sel}_{usuario_actual}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.success("🎉 No se detectaron excepciones pendientes para el personal asignado en este período.")

        # TAB 2: CANJE MASIVO
        with tab_canje_masivo:
            st.subheader("⚖️ Canje Masivo de Horas Extras por Faltas")
            if df_canje_resumen is not None and not df_canje_resumen.empty:
                if not es_editable:
                    st.info("🔒 **Edición Bloqueada:** Para realizar canjes, presione el botón **'▶️ Marcar EN PROCESO'** arriba.")

                if not es_editable:
                    cols_deshabilitadas_canje = list(df_canje_resumen.columns)
                else:
                    cols_deshabilitadas_canje = [c for c in ["Carnet_Identidad", "ID", "Nombre", "Turno Dominante", "Horas Costo por Día", "Bolsa HE Acumulada (hrs)", "Días Máx. Canjeables", "Faltas Registradas"] if c in df_canje_resumen.columns]

                df_edited_canje = st.data_editor(
                    df_canje_resumen,
                    use_container_width=True,
                    hide_index=True,
                    disabled=cols_deshabilitadas_canje,
                    column_config={
                        "Carnet_Identidad": st.column_config.Column(disabled=True),
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

                dias_totales_canjeados = df_edited_canje['Días a Canjear (Aplicar)'].sum() if 'Días a Canjear (Aplicar)' in df_edited_canje.columns else 0
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
                    id_emp_reg = clean_ci(st.text_input("ID / Carnet Empleado:*"))
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
                        st.error("No se pueden registrar regularizaciones cuando el período no está EN PROCESO.")
                    else:
                        audit_log.registrar_evento(
                            usuario_pin=usuario_actual,
                            usuario_nombre=usuario_actual,
                            accion="REGULARIZACION_OMISION",
                            modulo="Aprobaciones",
                            detalles={"empleado": nombre_emp_reg, "ci": id_emp_reg, "fecha": str(fecha_reg), "tipo": tipo_marcacion, "motivo": motivo_reg}
                        )
                        st.success(f"Regularización registrada para {nombre_emp_reg} el día {fecha_reg}.")

    except Exception as e:
        st.error(f"Error en el módulo de Aprobaciones: {e}")

# -----------------------------------------------------------------------------
# 5. VALORES MONETIZADOS
# -----------------------------------------------------------------------------
elif opcion == "💵 Valores Monetizados":
    st.header("💵 Gestión de Valores Monetizados y Tarifas de Jornaleros")
    st.caption("Módulo exclusivo para Superusuarios. Permite configurar y aprobar tarifas de jornaleros con almacenamiento en disco.")

    # Verificación de Rol
    roles_super = ["RESPONSABLE_OPERACIONES", "JEFE_PRODUCCION", "Jefe de Producción", "ADMINISTRADOR", "Superusuario"]
    if rol_actual not in roles_super:
        st.error("⛔ Acceso denegado: Esta pantalla requiere privilegios de Superusuario.")
        st.stop()

    # Cargar Períodos Disponibles desde Biométrico o Default
    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos_tarifas = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True)
    except Exception:
        periodos_tarifas = [datetime.now().strftime('%Y-%m')]

    col_p_tarifa, _ = st.columns([2, 2])
    periodo_tarifa_sel = col_p_tarifa.selectbox("🗓️ Seleccionar Período/Gestión de Tarifas:", options=periodos_tarifas)

    # Cargar Configuración del Período de Forma Persistente
    config = obtener_config_periodo_persistent(periodo_tarifa_sel)

    st.subheader(f"1. Tarifas Base Globales ({periodo_tarifa_sel})")
    col1, col2 = st.columns(2)

    with col1:
        diurno_norm = st.number_input("Diurno Normal [Bs]", value=float(config.get("tarifas_base", {}).get("diurno_normal", 100.0)), step=5.0)
        diurno_15 = st.number_input("Diurno 1.5 [Bs]", value=float(config.get("tarifas_base", {}).get("diurno_1_5", 150.0)), step=5.0)

    with col2:
        nocturno_norm = st.number_input("Nocturno Normal [Bs]", value=float(config.get("tarifas_base", {}).get("nocturno_normal", 120.0)), step=5.0)
        nocturno_15 = st.number_input("Nocturno 1.5 [Bs]", value=float(config.get("tarifas_base", {}).get("nocturno_1_5", 180.0)), step=5.0)

    if st.button("💾 Guardar Tarifas Base", type="primary"):
        config["tarifas_base"] = {
            "diurno_normal": diurno_norm,
            "diurno_1_5": diurno_15,
            "nocturno_normal": nocturno_norm,
            "nocturno_1_5": nocturno_15
        }
        if guardar_config_periodo_persistent(periodo_tarifa_sel, config):
            audit_log.registrar_evento(usuario_actual, usuario_actual, "ACTUALIZAR_TARIFAS_BASE", "Tarifas", {"periodo": periodo_tarifa_sel, "tarifas": config["tarifas_base"]})
            st.success(f"✅ Tarifas base guardadas exitosamente en disco para la gestión {periodo_tarifa_sel}")

    st.divider()

    st.subheader(f"2. Excepciones Tarifarias por Empleado ({periodo_tarifa_sel})")

    # Cargar Maestro de Empleados y Filtrar ÚNICAMENTE JORNALEROS
    dict_jornaleros = {}
    try:
        df_emp_all = cached_load_sheet_data("01_Maestro_Empleados")
        col_tipo = [c for c in df_emp_all.columns if str(c).strip().lower() in ['tipo_personal', 'tipo personal']][0]
        col_nombre_emp = [c for c in df_emp_all.columns if str(c).strip().lower() in ['nombre_completo', 'nombre']][0]
        col_ci_emp = [c for c in df_emp_all.columns if str(c).strip().lower() in ['carnet_identidad', 'ci', 'carnet']][0]

        df_jornaleros = df_emp_all[df_emp_all[col_tipo].astype(str).str.strip().str.upper() == 'JORNALERO'].copy()
        for _, row in df_jornaleros.iterrows():
            nom = str(row[col_nombre_emp]).strip()
            ci_val = clean_ci(row[col_ci_emp])
            dict_jornaleros[nom] = ci_val
    except Exception as e:
        st.error(f"Error cargando lista de Jornaleros: {e}")

    c_nom, c_tipo, c_monto = st.columns([3, 3, 2])

    if dict_jornaleros:
        nombre_sel = c_nom.selectbox("Seleccionar Jornalero (Por Nombre):", options=sorted(list(dict_jornaleros.keys())))
        ci_vinculado = dict_jornaleros[nombre_sel]
    else:
        nombre_sel = c_nom.text_input("Nombre de Jornalero")
        ci_vinculado = ""

    tipo_in = c_tipo.selectbox("Tipo de Turno", [
        ("diurno_normal", "Diurno Normal"),
        ("diurno_1_5", "Diurno 1.5"),
        ("nocturno_normal", "Nocturno Normal"),
        ("nocturno_1_5", "Nocturno 1.5")
    ], format_func=lambda x: x[1])

    # Carga automática del monto guardado si existe previamente
    excepciones_actuales = config.get("excepciones", {})
    monto_guardado = excepciones_actuales.get(ci_vinculado, {}).get(tipo_in[0], 0.0)

    monto_in = c_monto.number_input(
        "Monto Personalizado [Bs]", 
        min_value=0.0, 
        value=float(monto_guardado), 
        step=5.0,
        key=f"monto_inp_{ci_vinculado}_{tipo_in[0]}"
    )

    if st.button("➕ Registrar / Actualizar Excepción"):
        if ci_vinculado:
            actualizar_excepcion_empleado_persistent(ci_vinculado, tipo_in[0], monto_in, periodo=periodo_tarifa_sel)
            audit_log.registrar_evento(usuario_actual, usuario_actual, "EXCEPCION_TARIFA", "Tarifas", {"periodo": periodo_tarifa_sel, "CI": ci_vinculado, "nombre": nombre_sel, "tipo": tipo_in[0], "monto": monto_in})
            st.success(f"Excepción guardada en disco para {nombre_sel} (CI: {ci_vinculado}) con el monto {monto_in} Bs.")
            st.rerun()
        else:
            st.warning("No se pudo obtener el CI del jornalero seleccionado.")

    excepciones = config.get("excepciones", {})
    if excepciones:
        st.write(f"**Excepciones Registradas Actuales ({periodo_tarifa_sel}):**")
        list_e = []
        mapa_ci_nombre = {v: k for k, v in dict_jornaleros.items()}

        for ci_raw, t_dict in excepciones.items():
            ci_clean = clean_ci(ci_raw)
            nom_mostrar = mapa_ci_nombre.get(ci_clean, "Desconocido / No encontrado")
            for t_type, m in t_dict.items():
                list_e.append({"Nombre_Empleado": nom_mostrar, "Carnet_Identidad": ci_clean, "Tipo_Turno": t_type, "Monto_Excepcion_Bs": m})
        st.dataframe(pd.DataFrame(list_e), use_container_width=True)

        list_opciones_del = [f"{mapa_ci_nombre.get(clean_ci(ci), ci)} (CI: {clean_ci(ci)})" for ci in excepciones.keys()]
        emp_del_sel = st.selectbox("Seleccionar Empleado para borrar excepciones:", list_opciones_del)

        if st.button("🗑️ Eliminar Excepción"):
            ci_del = clean_ci(emp_del_sel.split("(CI: ")[-1].replace(")", "").strip())
            eliminar_excepcion_empleado_persistent(ci_del, periodo=periodo_tarifa_sel)
            audit_log.registrar_evento(usuario_actual, usuario_actual, "ELIMINAR_EXCEPCION_TARIFA", "Tarifas", {"periodo": periodo_tarifa_sel, "CI": ci_del})
            st.info(f"Excepciones eliminadas para CI: {ci_del}")
            st.rerun()

    # --- PANEL DE RESPALDO Y RESTAURACIÓN DE TARIFAS ---
    with st.expander("🛡️ Resguardo y Respaldo de Tarifas (.json)"):
        st.caption("Descargue o restaure la configuración de tarifas base y excepciones registradas en disco:")
        c_tar_exp, c_tar_imp = st.columns(2)
        
        with c_tar_exp:
            all_tarifas_json = json.dumps(cargar_todas_tarifas_json(), ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 Descargar Respaldo de Tarifas (.json)",
                data=all_tarifas_json,
                file_name=f"tarifas_config_backup_{periodo_tarifa_sel}.json",
                mime="application/json"
            )

        with c_tar_imp:
            file_tar = st.file_uploader("📤 Restaurar Tarifas desde Respaldo", type=["json"], key="uploader_tarifas_backup")
            if file_tar is not None:
                try:
                    data_rest = json.loads(file_tar.read().decode("utf-8"))
                    if guardar_todas_tarifas_json(data_rest):
                        st.success("✅ Tarifas y excepciones restauradas con éxito.")
                        st.rerun()
                except Exception as err:
                    st.error(f"Error al restaurar archivo: {err}")

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

# -----------------------------------------------------------------------------
# 7. BITÁCORA DE AUDITORÍA
# -----------------------------------------------------------------------------
elif opcion == "📜 Bitácora de Auditoría":
    st.header("📜 Bitácora de Auditoría e Historial de Cambios")
    st.caption("Registro inalterable de acciones realizadas por los supervisores en el sistema.")

    df_logs = audit_log.obtener_logs(limite=1000)

    if not df_logs.empty:
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            usuarios_log = ["Todos"] + list(df_logs['Usuario'].dropna().unique())
            u_sel = st.selectbox("Filtrar por Usuario:", usuarios_log)
        with col_b2:
            modulos_log = ["Todos"] + list(df_logs['Módulo'].dropna().unique())
            m_sel = st.selectbox("Filtrar por Módulo:", modulos_log)

        df_logs_fil = df_logs.copy()
        if u_sel != "Todos":
            df_logs_fil = df_logs_fil[df_logs_fil['Usuario'] == u_sel]
        if m_sel != "Todos":
            df_logs_fil = df_logs_fil[df_logs_fil['Módulo'] == m_sel]

        st.dataframe(df_logs_fil, use_container_width=True, hide_index=True)

        buffer_log = io.BytesIO()
        with pd.ExcelWriter(buffer_log, engine='openpyxl') as writer:
            df_logs_fil.to_excel(writer, sheet_name='Bitacora_Auditoria', index=False)
        
        st.download_button(
            label="📥 Descargar Bitácora en Excel",
            data=buffer_log.getvalue(),
            file_name=f"Bitacora_Auditoria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("ℹ️ Aún no existen registros en la bitácora de auditoría.")
