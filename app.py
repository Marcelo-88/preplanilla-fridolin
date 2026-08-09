import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime

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

TARIFAS_JSON_PATH = "tarifas_config.json"

def cargar_todas_tarifas_json():
    if os.path.exists(TARIFAS_JSON_PATH):
        try:
            with open(TARIFAS_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_todas_tarifas_json(data):
    try:
        with open(TARIFAS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

@st.cache_resource
def get_managers():
    return AuditLogger(), LockManager(), NovedadesManager(), DBManager()

audit_log, lock_mgr, nov_mgr, db_mgr = get_managers()

@st.cache_data(ttl=300, show_spinner=False)
def cached_load_sheet_data(sheet_name):
    return load_sheet_data(sheet_name)

st.set_page_config(page_title="Pre-Planilla Fridolin", page_icon="🏭", layout="wide")
st.title("🏭 Control de Asistencia y Reportes - Fridolin")

st.sidebar.image("https://em-content.zobj.net/source/apple/354/factory_1f3ed.png", width=80)
st.sidebar.title("Menú Principal")

try:
    df_emp_master = cached_load_sheet_data("01_Maestro_Empleados")
    usuario_actual, rol_actual, empleados_permitidos, pin_ok = render_user_selector(df_emp_master)
except Exception as e:
    usuario_actual, rol_actual, empleados_permitidos, pin_ok = "Invitado", "Jefe de Producción", [], True
    st.sidebar.error(str(e))

st.sidebar.divider()
opcion = st.sidebar.radio("Seleccione una vista:", [
    "📊 Parámetros y Reglas",
    "⏱️ Importación Biométrico",
    "📝 Novedades y Permisos",
    "✅ Aprobaciones Supervisores",
    "💵 Valores Monetizados",
    "📑 Pre-Planilla y Reportes",
    "📜 Bitácora de Auditoría"
])
st.sidebar.divider()
st.sidebar.caption("v2.5 - Filtro restaurado + Guardado de decisiones")

# 1. PARÁMETROS
if opcion == "📊 Parámetros y Reglas":
    st.header("⚙️ Parámetros y Reglas")
    data = [
        {"Parámetro": "Tolerancia Atraso", "Valor": "10 min", "Descripción": "Todo o Nada"},
        {"Parámetro": "Tiempo Comida", "Valor": "30 min", "Descripción": "Descuento automático 0.5h"},
        {"Parámetro": "Jornada Diurna", "Valor": "07:00-15:30", "Descripción": "8h netas = 1 turno"},
        {"Parámetro": "Jornada Nocturna", "Valor": "22:00-05:30", "Descripción": "7h netas = 1 turno"},
    ]
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

# 2. BIOMÉTRICO
elif opcion == "⏱️ Importación Biométrico":
    st.header("⏱️ Importación Biométrico")
    try:
        df = cached_load_sheet_data("02_Importacion_Biometrico")
        st.success(f"{len(df)} registros") if df is not None else st.warning("Sin datos")
        if df is not None:
            st.dataframe(df.head(30), use_container_width=True)
    except Exception as e:
        st.error(str(e))

# 3. NOVEDADES
elif opcion == "📝 Novedades y Permisos":
    st.header("📝 Novedades y Permisos")
    dict_nombre_ci = {}
    try:
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        cols = {str(c).lower(): c for c in df_emp.columns}
        c_nom = next((cols[k] for k in cols if 'nombre' in k), None)
        c_ci = next((cols[k] for k in cols if any(x in k for x in ['carnet','ci','id'])), None)
        if c_nom and c_ci:
            df_f = df_emp[df_emp[c_nom].astype(str).str.strip().isin(empleados_permitidos)] if empleados_permitidos else df_emp
            for _, r in df_f.iterrows():
                dict_nombre_ci[str(r[c_nom]).strip()] = clean_ci(r[c_ci])
    except:
        pass

    with st.form("form_nov"):
        c1, c2 = st.columns(2)
        with c1:
            if dict_nombre_ci:
                emp_nombre = st.selectbox("Nombre*", sorted(dict_nombre_ci.keys()))
                emp_id = dict_nombre_ci[emp_nombre]
                st.text_input("CI*", value=emp_id, disabled=True)
            else:
                emp_id = st.text_input("CI*")
                emp_nombre = st.text_input("Nombre*")
            tipo = st.selectbox("Tipo*", nov_mgr.obtener_tipos_novedad())
        with c2:
            f_ini = st.date_input("Inicio*")
            f_fin = st.date_input("Fin*")
            just = st.text_area("Justificación")
        if st.form_submit_button("Registrar"):
            if emp_id and emp_nombre:
                res = nov_mgr.registrar_novedad(emp_id, emp_nombre, tipo, str(f_ini), str(f_fin), just, usuario_actual)
                st.success(res["mensaje"]) if res.get("exito") else st.error(res.get("mensaje"))

    st.subheader("Novedades Registradas")
    todas = nov_mgr.obtener_todas_novedades()
    st.dataframe(pd.DataFrame(todas), use_container_width=True) if todas else st.info("Sin novedades")

# 4. APROBACIONES (CON FILTRO + GUARDADO)
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Panel de Aprobaciones de Supervisores")
    st.caption("Modo temporal: cálculo sin consultar novedades (rápido)")

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True) or [datetime.now().strftime('%Y-%m')]
        periodo_sel = st.selectbox("Período:", periodos)

        estado = lock_mgr.obtener_estado_periodo(periodo_sel, usuario=usuario_actual)
        es_editable = lock_mgr.es_editable(periodo_sel, rol_actual, usuario=usuario_actual)

        c1, c2, c3 = st.columns(3)
        c1.metric("Estado", estado)
        with c2:
            if st.button("▶️ EN PROCESO"):
                res = lock_mgr.cambiar_estado(periodo_sel, "EN_PROCESO", usuario_actual, rol_actual, usuario_actual)
                st.success(res["mensaje"]) if res["exito"] else st.error(res["mensaje"])
                st.rerun()
        with c3:
            if st.button("🔒 FINALIZAR", type="primary"):
                res = lock_mgr.cambiar_estado(periodo_sel, "FINALIZADO", usuario_actual, rol_actual, usuario_actual)
                if res["exito"]:
                    st.success(res["mensaje"])
                    st.rerun()

        st.divider()

        if st.button("🔄 Cargar Excepciones del Período", type="primary"):
            with st.spinner("Procesando marcaciones..."):
                df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
                df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                df_bio_p = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == periodo_sel].copy()

                # Temporal: sin novedades para velocidad
                df_res = process_attendance(df_bio_p, df_params, None, df_emp, None)
                df_exc = detect_exceptions(df_res)

                if empleados_permitidos and rol_actual != "Jefe de Producción":
                    try:
                        df_exc = filter_dataframe_by_supervisor(df_exc, "Nombre", empleados_permitidos, rol_actual)
                    except:
                        pass

                st.session_state['df_exc'] = df_exc
                st.session_state['periodo_cargado'] = periodo_sel
                st.success(f"Se cargaron {len(df_exc) if df_exc is not None else 0} excepciones.")

        if 'df_exc' in st.session_state and st.session_state.get('periodo_cargado') == periodo_sel:
            df_exc = st.session_state['df_exc']

            if df_exc is not None and not df_exc.empty:
                # Filtros
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    tipos = ["Todos"] + sorted(df_exc.get("Tipo Excepción", pd.Series()).dropna().unique().tolist())
                    sel_tipo = st.selectbox("Filtrar por Tipo:", tipos)
                with col_f2:
                    empleados = ["Todos"] + sorted(df_exc.get("Nombre", pd.Series()).dropna().unique().tolist())
                    sel_emp = st.selectbox("Filtrar por Empleado:", empleados)

                df_fil = df_exc.copy()
                if sel_tipo != "Todos":
                    df_fil = df_fil[df_fil["Tipo Excepción"] == sel_tipo]
                if sel_emp != "Todos":
                    df_fil = df_fil[df_fil["Nombre"] == sel_emp]

                st.caption(f"Mostrando {len(df_fil)} de {len(df_exc)} excepciones")

                df_edited = st.data_editor(
                    df_fil,
                    use_container_width=True,
                    hide_index=True,
                    disabled=not es_editable,
                    key=f"editor_{periodo_sel}_{sel_emp}_{sel_tipo}",
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

                if es_editable and st.button("💾 Guardar Decisiones", type="primary"):
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
                            "observaciones": "",
                            "registrado_por": usuario_actual
                        }
                        if db_mgr.guardar_decision(data).get("exito"):
                            guardadas += 1
                    st.success(f"✅ {guardadas} decisiones guardadas correctamente.")
            else:
                st.success("No hay excepciones en este período.")
        else:
            st.info("Haz clic en **Cargar Excepciones del Período** para ver las anomalías.")

    except Exception as e:
        st.error(str(e))

# 5. VALORES
elif opcion == "💵 Valores Monetizados":
    st.header("💵 Valores Monetizados")
    st.info("Módulo de tarifas.")

# 6. PRE-PLANILLA
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("📑 Pre-Planilla")
    st.info("Seleccione período y procese desde Aprobaciones primero.")

# 7. BITÁCORA
elif opcion == "📜 Bitácora de Auditoría":
    st.header("📜 Bitácora")
    logs = audit_log.obtener_logs(300)
    st.dataframe(pd.DataFrame(logs), use_container_width=True) if logs else st.info("Sin registros")
