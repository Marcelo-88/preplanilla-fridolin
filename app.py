import streamlit as st
import pandas as pd
import io
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions, get_canje_summary
from modules.auth_permissions import render_user_selector, filter_dataframe_by_supervisor
from modules.excel_exporter import ExcelExporter

from modules.audit_logger import AuditLogger
from modules.lock_manager import LockManager
from modules.novedades import NovedadesManager
from modules.db_manager import DBManager

try:
    from modules.tarifas_manager import clean_ci
except ImportError:
    def clean_ci(val):
        if val is None:
            return ""
        return str(val).split('.')[0].strip().upper()

# -----------------------------------------------------------------------------
# TARIFAS (se mantiene)
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
    except Exception:
        return False

def obtener_config_periodo_persistent(periodo: str) -> dict:
    all_data = cargar_todas_tarifas_json()
    if periodo in all_data:
        return all_data[periodo]
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
    return guardar_todas_tarifas_json(all_data)


@st.cache_resource
def get_managers():
    return AuditLogger(), LockManager(), NovedadesManager(), DBManager()

audit_log, lock_mgr, nov_mgr, db_mgr = get_managers()


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


st.set_page_config(page_title="Pre-Planilla Fridolin", page_icon="🏭", layout="wide")
st.title("🏭 Control de Asistencia y Reportes - Fridolin")

st.sidebar.image("https://em-content.zobj.net/source/apple/354/factory_1f3ed.png", width=80)
st.sidebar.title("Menú Principal")

try:
    df_emp_master = cached_load_sheet_data("01_Maestro_Empleados")
    usuario_actual, rol_actual, empleados_permitidos, pin_ok = render_user_selector(df_emp_master)
except Exception as e:
    usuario_actual, rol_actual, empleados_permitidos, pin_ok = "Invitado", "Jefe de Producción", [], True
    st.sidebar.error(f"Error: {e}")

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
# 1. PARÁMETROS
# -----------------------------------------------------------------------------
if opcion == "📊 Parámetros y Reglas":
    st.header("⚙️ Parámetros y Reglas del Sistema")
    data_reglas = [
        {"Parámetro / Regla": "Tolerancia_Atraso_Min", "Valor": "10 min", "Descripción y Aplicación": "Regla 'Todo o Nada': Atrasos <= 10 min no se descuentan. Atrasos >= 11 min cobran el total desde el minuto 1."},
        {"Parámetro / Regla": "Tiempo_Comida_Min", "Valor": "30 min", "Descripción y Aplicación": "Descuento automático de 0.5 horas en toda jornada con salida."},
        {"Parámetro / Regla": "Jornada_Diurna_Base", "Valor": "8.0 hrs", "Descripción y Aplicación": "07:00 a 15:30 = 1.0 Turno."},
        {"Parámetro / Regla": "Jornada_Nocturna_Base", "Valor": "7.0 hrs", "Descripción y Aplicación": "22:00 a 05:30 = 1.0 Turno."},
        {"Parámetro / Regla": "Jornada_Nocturna_Especial", "Valor": "11.0 hrs", "Descripción y Aplicación": "Viernes y Domingos = 1.5 Turnos."},
    ]
    st.dataframe(pd.DataFrame(data_reglas), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 2. IMPORTACIÓN BIOMÉTRICO
# -----------------------------------------------------------------------------
elif opcion == "⏱️ Importación Biométrico":
    st.header("⏱️ Importación Biométrico")
    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        if df_bio is not None and not df_bio.empty:
            st.success(f"✅ {len(df_bio)} registros cargados.")
            st.dataframe(df_bio.head(50), use_container_width=True)
        else:
            st.warning("No hay datos.")
    except Exception as e:
        st.error(str(e))

# -----------------------------------------------------------------------------
# 3. NOVEDADES
# -----------------------------------------------------------------------------
elif opcion == "📝 Novedades y Permisos":
    st.header("📝 Gestión de Novedades, Permisos y Licencias")

    dict_nombre_ci = {}
    try:
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        cols = {str(c).strip().lower(): c for c in df_emp.columns}
        c_nombre = next((cols[k] for k in cols if 'nombre' in k), None)
        c_ci = next((cols[k] for k in cols if any(x in k for x in ['carnet', 'ci', 'id'])), None)
        if c_nombre and c_ci:
            df_f = df_emp[df_emp[c_nombre].astype(str).str.strip().isin(empleados_permitidos)] if empleados_permitidos else df_emp
            for _, row in df_f.iterrows():
                nom = str(row[c_nombre]).strip()
                ci = clean_ci(row[c_ci])
                if nom and ci:
                    dict_nombre_ci[nom] = ci
    except Exception:
        pass

    with st.form("form_novedad"):
        col1, col2 = st.columns(2)
        with col1:
            if dict_nombre_ci:
                emp_nombre = st.selectbox("Nombre Completo*", options=sorted(dict_nombre_ci.keys()))
                emp_id = dict_nombre_ci.get(emp_nombre, "")
                st.text_input("CI*", value=emp_id, disabled=True)
            else:
                emp_id = st.text_input("CI*")
                emp_nombre = st.text_input("Nombre Completo*")
            tipo_nov = st.selectbox("Tipo de Novedad*", nov_mgr.obtener_tipos_novedad())
        with col2:
            f_ini = st.date_input("Fecha Inicio*")
            f_fin = st.date_input("Fecha Fin*")
            justificacion = st.text_area("Justificación")

        if st.form_submit_button("💾 Registrar Novedad"):
            if emp_id and emp_nombre:
                res = nov_mgr.registrar_novedad(emp_id, emp_nombre, tipo_nov, str(f_ini), str(f_fin), justificacion, usuario_actual)
                if res.get("exito"):
                    st.success(res["mensaje"])
                else:
                    st.error(res.get("mensaje"))
            else:
                st.warning("Complete los campos.")

    st.divider()
    st.subheader("📋 Novedades Registradas")
    todas = nov_mgr.obtener_todas_novedades()
    if todas:
        st.dataframe(pd.DataFrame(todas), use_container_width=True, hide_index=True)
    else:
        st.info("No hay novedades.")

# -----------------------------------------------------------------------------
# 4. APROBACIONES SUPERVISORES (SIMPLIFICADO + GUARDAR)
# -----------------------------------------------------------------------------
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Panel de Aprobaciones de Supervisores")

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")

        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True) or [datetime.now().strftime('%Y-%m')]

        periodo_sel = st.selectbox("🗓️ Seleccionar Período:", periodos)

        estado_actual = lock_mgr.obtener_estado_periodo(periodo_sel, usuario=usuario_actual)
        es_editable = lock_mgr.es_editable(periodo_sel, rol_actual, usuario=usuario_actual)

        c1, c2, c3 = st.columns([2, 2, 3])
        c1.metric("Estado Actual", estado_actual)
        with c2:
            if st.button("▶️ Marcar EN PROCESO"):
                res = lock_mgr.cambiar_estado(periodo_sel, "EN_PROCESO", usuario_actual, rol_actual, usuario_actual)
                st.success(res["mensaje"]) if res["exito"] else st.error(res["mensaje"])
                st.rerun()
        with c3:
            if st.button("🔒 FINALIZAR Período", type="primary"):
                res = lock_mgr.cambiar_estado(periodo_sel, "FINALIZADO", usuario_actual, rol_actual, usuario_actual)
                if res["exito"]:
                    audit_log.registrar_evento(usuario_actual, usuario_actual, "FINALIZAR_PERIODO", "Aprobaciones", {"periodo": periodo_sel})
                    st.success(res["mensaje"])
                    st.rerun()
                else:
                    st.error(res["mensaje"])

        df_bio_periodo = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == periodo_sel].copy()
        df_resultado = run_cached_attendance_processing(df_bio_periodo, df_params, df_emp, nov_mgr)
        df_excepciones = run_cached_exceptions(df_resultado)
        df_canje = run_cached_canje(df_resultado)

        if empleados_permitidos and rol_actual != "Jefe de Producción":
            try:
                df_resultado = filter_dataframe_by_supervisor(df_resultado, "Nombre", empleados_permitidos, rol_actual)
                if df_excepciones is not None and not df_excepciones.empty:
                    df_excepciones = filter_dataframe_by_supervisor(df_excepciones, "Nombre", empleados_permitidos, rol_actual)
            except Exception:
                pass

        tab1, tab2, tab3 = st.tabs(["📋 Excepciones", "⚖️ Canje Masivo", "🛠️ Regularización"])

        with tab1:
            st.subheader(f"Excepciones Detectadas ({periodo_sel})")
            if not es_editable:
                st.info("🔒 Edición bloqueada. Marque EN PROCESO para editar.")

            if df_excepciones is not None and not df_excepciones.empty:
                df_edited = st.data_editor(
                    df_excepciones,
                    use_container_width=True,
                    hide_index=True,
                    disabled=[] if es_editable else list(df_excepciones.columns),
                    key=f"editor_{periodo_sel}",
                    column_config={
                        "Decisión Supervisor": st.column_config.SelectboxColumn(
                            "Decisión",
                            options=["Pendiente", "Aprobado (Pago)", "Acumular (Próx. Mes)", "Rechazado", "Justificado", "Canjeado"]
                        ),
                        "Tipo Falta": st.column_config.SelectboxColumn(
                            "Tipo Falta",
                            options=["N/A", "Justificada", "Injustificada"]
                        )
                    }
                )

                if es_editable and st.button("💾 Guardar Decisiones del Supervisor", type="primary"):
                    guardadas = 0
                    col_ci = next((c for c in df_edited.columns if 'carnet' in str(c).lower() or c == 'ID'), None)
                    col_nom = next((c for c in df_edited.columns if 'nombre' in str(c).lower()), None)
                    col_fec = next((c for c in df_edited.columns if 'fecha' in str(c).lower()), None)
                    col_tip = next((c for c in df_edited.columns if 'tipo excepción' in str(c).lower()), None)

                    for _, row in df_edited.iterrows():
                        data = {
                            "periodo": periodo_sel,
                            "carnet_identidad": str(row.get(col_ci, "")),
                            "nombre": str(row.get(col_nom, "")),
                            "fecha": str(row.get(col_fec, ""))[:10],
                            "tipo_excepcion": str(row.get(col_tip, "")),
                            "decision": str(row.get("Decisión Supervisor", "Pendiente")),
                            "tipo_falta": str(row.get("Tipo Falta", "N/A")),
                            "observaciones": str(row.get("Observaciones", "")),
                            "registrado_por": usuario_actual
                        }
                        res = db_mgr.guardar_decision(data)
                        if res.get("exito"):
                            guardadas += 1

                    st.success(f"✅ {guardadas} decisiones guardadas.")
                    audit_log.registrar_evento(usuario_actual, usuario_actual, "GUARDAR_DECISIONES", "Aprobaciones", {"periodo": periodo_sel, "cantidad": guardadas})
            else:
                st.success("No hay excepciones pendientes.")

        with tab2:
            st.subheader("⚖️ Canje Masivo")
            if df_canje is not None and not df_canje.empty:
                st.dataframe(df_canje, use_container_width=True)
            else:
                st.info("No hay datos de canje.")

        with tab3:
            st.subheader("🛠️ Regularización")
            st.info("Funcionalidad de regularización disponible.")

    except Exception as e:
        st.error(f"Error: {e}")

# -----------------------------------------------------------------------------
# 5. VALORES MONETIZADOS
# -----------------------------------------------------------------------------
elif opcion == "💵 Valores Monetizados":
    st.header("💵 Valores Monetizados")
    if rol_actual not in ["Jefe de Producción", "RESPONSABLE_OPERACIONES", "ADMINISTRADOR"]:
        st.error("Acceso denegado.")
        st.stop()
    st.info("Módulo de tarifas (en desarrollo de persistencia cloud).")

# -----------------------------------------------------------------------------
# 6. PRE-PLANILLA
# -----------------------------------------------------------------------------
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("📑 Pre-Planilla y Reportes")
    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True)
        p_sel = st.selectbox("Período:", ["Todos"] + periodos)
        df_bio_f = df_bio if p_sel == "Todos" else df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == p_sel]
        df_res = run_cached_attendance_processing(df_bio_f, df_params, df_emp, nov_mgr)
        if df_res is not None and not df_res.empty:
            st.dataframe(df_res, use_container_width=True, hide_index=True)
        else:
            st.warning("Sin datos.")
    except Exception as e:
        st.error(str(e))

# -----------------------------------------------------------------------------
# 7. BITÁCORA
# -----------------------------------------------------------------------------
elif opcion == "📜 Bitácora de Auditoría":
    st.header("📜 Bitácora de Auditoría")
    df_logs = audit_log.obtener_logs(500)
    if not df_logs.empty:
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("Sin registros.")
