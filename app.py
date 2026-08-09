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
    "🔄 Canje de Horas",
    "💵 Valores Monetizados",
    "📑 Pre-Planilla y Reportes",
    "📜 Bitácora de Auditoría"
])
st.sidebar.divider()
st.sidebar.caption("v2.6.1 - Guardado de decisiones corregido")

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
                if res.get("exito"):
                    st.success(res["mensaje"])
                else:
                    st.error(res.get("mensaje"))

    st.subheader("Novedades Registradas")
    todas = nov_mgr.obtener_todas_novedades()
    if todas:
        st.dataframe(pd.DataFrame(todas), use_container_width=True, hide_index=True)
    else:
        st.info("Sin novedades registradas")

# 4. APROBACIONES (GUARDADO CORREGIDO)
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Panel de Aprobaciones de Supervisores")

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
            with st.spinner("Procesando marcaciones y cargando decisiones..."):
                df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
                df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                df_bio_p = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == periodo_sel].copy()

                df_res = process_attendance(df_bio_p, df_params, None, df_emp, None)
                df_exc = detect_exceptions(df_res)

                if empleados_permitidos and rol_actual != "Jefe de Producción":
                    try:
                        df_exc = filter_dataframe_by_supervisor(df_exc, "Nombre", empleados_permitidos, rol_actual)
                    except:
                        pass

                # Cargar decisiones ya guardadas
                if df_exc is not None and not df_exc.empty:
                    decisiones = db_mgr.obtener_decisiones_periodo(periodo_sel)
                    if decisiones:
                        df_dec = pd.DataFrame(decisiones)
                        col_ci = next((c for c in df_exc.columns if 'carnet' in str(c).lower() or str(c).upper() == 'ID'), None)
                        col_fecha = next((c for c in df_exc.columns if 'fecha' in str(c).lower()), None)

                        if col_ci and col_fecha and 'carnet_identidad' in df_dec.columns:
                            df_exc = df_exc.copy()
                            df_exc['_key'] = df_exc[col_ci].astype(str).str.strip() + "_" + df_exc[col_fecha].astype(str).str[:10]
                            df_dec['_key'] = df_dec['carnet_identidad'].astype(str).str.strip() + "_" + df_dec['fecha'].astype(str).str[:10]

                            mapa_dec = dict(zip(df_dec['_key'], df_dec.get('decision', '')))
                            mapa_tf = dict(zip(df_dec['_key'], df_dec.get('tipo_falta', '')))

                            for col_dec in ['Decisión Supervisor', 'Decisión', 'decision']:
                                if col_dec in df_exc.columns:
                                    df_exc[col_dec] = df_exc['_key'].map(mapa_dec).fillna(df_exc[col_dec])
                                    break
                            for col_tf in ['Tipo Falta', 'Tipo Falta (Para Contabilidad)', 'tipo_falta']:
                                if col_tf in df_exc.columns:
                                    df_exc[col_tf] = df_exc['_key'].map(mapa_tf).fillna(df_exc[col_tf])
                                    break

                            df_exc.drop(columns=['_key'], inplace=True, errors='ignore')

                st.session_state['df_exc'] = df_exc
                st.session_state['periodo_cargado'] = periodo_sel
                st.success(f"Se cargaron {len(df_exc) if df_exc is not None else 0} excepciones.")

        if 'df_exc' in st.session_state and st.session_state.get('periodo_cargado') == periodo_sel:
            df_exc = st.session_state['df_exc']

            if df_exc is not None and not df_exc.empty:
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    tipos = ["Todos"] + sorted([str(x) for x in df_exc.get("Tipo Excepción", pd.Series()).dropna().unique()])
                    sel_tipo = st.selectbox("Filtrar por Tipo:", tipos)
                with col_f2:
                    empleados = ["Todos"] + sorted([str(x) for x in df_exc.get("Nombre", pd.Series()).dropna().unique()])
                    sel_emp = st.selectbox("Filtrar por Empleado:", empleados)

                df_fil = df_exc.copy()
                if sel_tipo != "Todos" and "Tipo Excepción" in df_fil.columns:
                    df_fil = df_fil[df_fil["Tipo Excepción"].astype(str) == sel_tipo]
                if sel_emp != "Todos" and "Nombre" in df_fil.columns:
                    df_fil = df_fil[df_fil["Nombre"].astype(str) == sel_emp]

                st.caption(f"Mostrando {len(df_fil)} de {len(df_exc)} excepciones")

                # Detectar nombres reales de columnas de decisión
                col_decision = next((c for c in df_fil.columns if 'decisión' in str(c).lower() or 'decision' in str(c).lower()), None)
                col_tipo_falta = next((c for c in df_fil.columns if 'tipo falta' in str(c).lower() or 'tipo_falta' in str(c).lower()), None)

                column_config = {}
                if col_decision:
                    column_config[col_decision] = st.column_config.SelectboxColumn(
                        "Decisión",
                        options=["Pendiente", "Aprobado (Pago)", "Acumular (Próx. Mes)", "Rechazado", "Justificado", "Canjeado"]
                    )
                if col_tipo_falta:
                    column_config[col_tipo_falta] = st.column_config.SelectboxColumn(
                        "Tipo Falta",
                        options=["N/A", "Justificada", "Injustificada"]
                    )

                df_edited = st.data_editor(
                    df_fil,
                    use_container_width=True,
                    hide_index=True,
                    disabled=not es_editable,
                    key=f"editor_{periodo_sel}_{sel_emp}_{sel_tipo}",
                    column_config=column_config
                )

                if es_editable and st.button("💾 Guardar Decisiones", type="primary"):
                    # Detección robusta de columnas
                    col_ci = next((c for c in df_edited.columns if 'carnet' in str(c).lower() or str(c).upper() in ['ID', 'CI']), None)
                    col_nom = next((c for c in df_edited.columns if 'nombre' in str(c).lower()), None)
                    col_fec = next((c for c in df_edited.columns if 'fecha' in str(c).lower()), None)
                    col_tip = next((c for c in df_edited.columns if 'tipo excepción' in str(c).lower() or 'tipo_excepcion' in str(c).lower()), None)
                    col_dec = next((c for c in df_edited.columns if 'decisión' in str(c).lower() or 'decision' in str(c).lower()), None)
                    col_tf = next((c for c in df_edited.columns if 'tipo falta' in str(c).lower() or 'tipo_falta' in str(c).lower()), None)

                    if not col_ci or not col_fec:
                        st.error(f"No se pudieron detectar columnas clave. Columnas disponibles: {list(df_edited.columns)}")
                    else:
                        guardadas = 0
                        errores = []

                        for idx, row in df_edited.iterrows():
                            data = {
                                "periodo": periodo_sel,
                                "carnet_identidad": str(row.get(col_ci, "")).strip(),
                                "nombre": str(row.get(col_nom, "")).strip() if col_nom else "",
                                "fecha": str(row.get(col_fec, ""))[:10],
                                "tipo_excepcion": str(row.get(col_tip, "")).strip() if col_tip else "",
                                "decision": str(row.get(col_dec, "Pendiente")).strip() if col_dec else "Pendiente",
                                "tipo_falta": str(row.get(col_tf, "N/A")).strip() if col_tf else "N/A",
                                "observaciones": "",
                                "registrado_por": usuario_actual
                            }

                            if not data["carnet_identidad"] or data["carnet_identidad"] == "nan":
                                continue

                            res = db_mgr.guardar_decision(data)
                            if res.get("exito"):
                                guardadas += 1
                            else:
                                errores.append(f"{data['nombre']}: {res.get('mensaje', 'Error desconocido')}")

                        if guardadas > 0:
                            st.success(f"✅ {guardadas} decisiones guardadas correctamente.")
                        if errores:
                            st.error("Errores al guardar:")
                            for e in errores[:5]:
                                st.write(f"- {e}")
                        if guardadas == 0 and not errores:
                            st.warning("No se guardó ninguna decisión. Revisa que haya cambios.")

                        st.rerun()
            else:
                st.success("No hay excepciones en este período.")
        else:
            st.info("Haz clic en **Cargar Excepciones del Período** para ver las anomalías.")

    except Exception as e:
        st.error(f"Error: {e}")

# 5. CANJE DE HORAS
elif opcion == "🔄 Canje de Horas":
    st.header("🔄 Canje de Horas Extras por Faltas")
    st.caption("Solo se usan las horas después del horario oficial marcadas como “Acumular (Próx. Mes)”")

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True) or [datetime.now().strftime('%Y-%m')]
        periodo_sel = st.selectbox("Período:", periodos, key="canje_periodo")

        decisiones = db_mgr.obtener_decisiones_periodo(periodo_sel)
        canjes_existentes = db_mgr.obtener_canjes_periodo(periodo_sel)

        if not decisiones:
            st.warning("No hay decisiones guardadas para este período. Primero ve a **Aprobaciones** y guarda las decisiones.")
        else:
            df_dec = pd.DataFrame(decisiones)
            df_acum = df_dec[df_dec['decision'].astype(str).str.contains("Acumular", case=False, na=False)].copy()

            if df_acum.empty:
                st.info("No hay horas marcadas como “Acumular (Próx. Mes)” en este período.")
            else:
                st.subheader("Horas disponibles para canje")
                st.dataframe(df_acum[["nombre", "fecha", "tipo_excepcion", "decision"]], use_container_width=True, hide_index=True)

                st.divider()
                st.subheader("Registrar un Canje")

                empleados_con_he = sorted(df_acum['nombre'].dropna().unique().tolist())
                emp_sel = st.selectbox("Empleado:", empleados_con_he)

                # Conteo simple de registros acumulados (placeholder)
                cant = len(df_acum[df_acum['nombre'] == emp_sel])
                st.info(f"Registros acumulados de {emp_sel}: **{cant}** (se calculará el valor real de horas más adelante)")

                dias_a_canjear = st.number_input("Días a canjear (1 día ≈ 8 hrs):", min_value=0.0, max_value=10.0, step=0.5, value=0.0)

                if st.button("💾 Guardar Canje", type="primary"):
                    if dias_a_canjear <= 0:
                        st.error("Indica al menos 0.5 días.")
                    else:
                        horas_usadas = dias_a_canjear * 8.0
                        ci_val = str(df_acum[df_acum['nombre'] == emp_sel]['carnet_identidad'].iloc[0]) if not df_acum[df_acum['nombre'] == emp_sel].empty else ""
                        data = {
                            "periodo": periodo_sel,
                            "carnet_identidad": ci_val,
                            "nombre": emp_sel,
                            "dias_canjeados": float(dias_a_canjear),
                            "horas_usadas": float(horas_usadas),
                            "faltas_afectadas": "",
                            "registrado_por": usuario_actual
                        }
                        res = db_mgr.guardar_canje(data)
                        if res.get("exito"):
                            st.success(f"✅ Canje de {dias_a_canjear} día(s) guardado para {emp_sel}")
                            st.rerun()
                        else:
                            st.error(res.get("mensaje", "Error al guardar canje"))

        st.divider()
        st.subheader("Canjes realizados en este período")
        if canjes_existentes:
            st.dataframe(pd.DataFrame(canjes_existentes), use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay canjes registrados.")

    except Exception as e:
        st.error(str(e))

# 6. VALORES
elif opcion == "💵 Valores Monetizados":
    st.header("💵 Valores Monetizados")
    st.info("Módulo de tarifas.")

# 7. PRE-PLANILLA
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("📑 Pre-Planilla")
    st.info("Seleccione período y procese desde Aprobaciones primero.")

# 8. BITÁCORA
elif opcion == "📜 Bitácora de Auditoría":
    st.header("📜 Bitácora")
    logs = audit_log.obtener_logs(300)
    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
    else:
        st.info("Sin registros")
