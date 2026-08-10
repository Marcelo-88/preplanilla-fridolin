import streamlit as st
import pandas as pd
from datetime import datetime, time

from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions
from modules.auth_permissions import render_user_selector
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

@st.cache_data(ttl=180, show_spinner="Cargando datos...")
def cached_load_sheet_data(sheet_name):
    try:
        return load_sheet_data(sheet_name)
    except Exception:
        return None

def obtener_cis_permitidos(df_emp, empleados_permitidos):
    """Convierte la lista de nombres permitidos a sus CI oficiales."""
    if df_emp is None or df_emp.empty or not empleados_permitidos:
        return set()

    cols = {str(c).lower(): c for c in df_emp.columns}
    c_nom = next((cols[k] for k in cols if 'nombre' in k), None)
    c_ci = next((cols[k] for k in cols if any(x in k for x in ['carnet', 'ci', 'id', 'codigo'])), None)

    if not c_nom or not c_ci:
        return set()

    cis = set()
    nombres_set = set(str(n).strip().upper() for n in empleados_permitidos)
    for _, row in df_emp.iterrows():
        nom = str(row[c_nom]).strip().upper()
        if nom in nombres_set:
            ci = clean_ci(row[c_ci])
            if ci:
                cis.add(ci)
    return cis

def filtrar_bio_por_ci(df_bio, cis_permitidos, rol_actual):
    """Filtra biométrico por CI (más confiable que por nombre)."""
    if df_bio is None or df_bio.empty:
        return df_bio
    if not cis_permitidos or rol_actual == "Jefe de Producción":
        return df_bio

    # Buscar columna de ID/CI en biométrico
    col_id = None
    for c in df_bio.columns:
        cl = str(c).lower()
        if any(x in cl for x in ['id', 'carnet', 'ci', 'codigo']):
            col_id = c
            break
    if col_id is None:
        col_id = df_bio.columns[0]

    def _match(val):
        return clean_ci(val) in cis_permitidos

    mask = df_bio[col_id].apply(_match)
    return df_bio[mask].copy()

def aplicar_decisiones_a_asistencia(df_res, decisiones, regularizaciones, canjes):
    if df_res is None or df_res.empty:
        return df_res

    df = df_res.copy()
    col_ci = next((c for c in df.columns if 'carnet' in str(c).lower() or str(c).upper() in ['ID', 'CI']), None)
    col_nom = next((c for c in df.columns if 'nombre' in str(c).lower()), None)
    col_fec = next((c for c in df.columns if 'fecha' in str(c).lower()), None)
    col_he = next((c for c in df.columns if 'horas extra' in str(c).lower() or 'horas_extra' in str(c).lower()), None)
    col_fj = next((c for c in df.columns if 'falta justificada' in str(c).lower()), None)
    col_fi = next((c for c in df.columns if 'falta injustificada' in str(c).lower()), None)
    col_atr = next((c for c in df.columns if 'atraso' in str(c).lower()), None)
    col_obs = next((c for c in df.columns if 'observacion' in str(c).lower()), None)

    if not col_ci or not col_fec:
        return df

    if col_he is None:
        df['Horas Extras'] = 0.0
        col_he = 'Horas Extras'
    if col_fj is None:
        df['Falta Justificada'] = 0
        col_fj = 'Falta Justificada'
    if col_fi is None:
        df['Falta Injustificada'] = 0
        col_fi = 'Falta Injustificada'
    if col_atr is None:
        df['Atraso (Minutos)'] = 0
        col_atr = 'Atraso (Minutos)'
    if col_obs is None:
        df['Observaciones'] = ""
        col_obs = 'Observaciones'

    df[col_he] = pd.to_numeric(df[col_he], errors='coerce').fillna(0.0)
    df[col_fj] = pd.to_numeric(df[col_fj], errors='coerce').fillna(0).astype(int)
    df[col_fi] = pd.to_numeric(df[col_fi], errors='coerce').fillna(0).astype(int)
    df[col_atr] = pd.to_numeric(df[col_atr], errors='coerce').fillna(0)
    df[col_obs] = df[col_obs].astype(str).replace(['nan', 'None', 'NaN'], '')
    df['_key'] = df[col_ci].astype(str).str.strip() + "_" + df[col_fec].astype(str).str[:10]

    if regularizaciones:
        df_reg = pd.DataFrame(regularizaciones)
        keys_reg = set()
        for _, r in df_reg.iterrows():
            f = str(r.get('fecha', ''))[:10]
            keys_reg.add(str(r.get('nombre', '')).strip() + "_" + f)
            if r.get('carnet_identidad'):
                keys_reg.add(str(r.get('carnet_identidad')).strip() + "_" + f)
        mask = df['_key'].isin(keys_reg) | (df[col_nom].astype(str).str.strip() + "_" + df[col_fec].astype(str).str[:10]).isin(keys_reg)
        df.loc[mask, col_fi] = 0
        df.loc[mask, col_fj] = 0
        df.loc[mask, col_atr] = 0
        df.loc[mask, col_obs] = df.loc[mask, col_obs] + " | Regularizado"

    if decisiones:
        df_dec = pd.DataFrame(decisiones)
        df_dec['_key'] = df_dec['carnet_identidad'].astype(str).str.strip() + "_" + df_dec['fecha'].astype(str).str[:10]
        for _, dec in df_dec.iterrows():
            key = dec['_key']
            decision = str(dec.get('decision', '')).strip()
            tipo_falta = str(dec.get('tipo_falta', 'N/A')).strip()
            mask = df['_key'] == key
            if not mask.any():
                continue
            obs = f" | {decision}"
            if tipo_falta and tipo_falta != 'N/A':
                obs += f" ({tipo_falta})"
            df.loc[mask, col_obs] = df.loc[mask, col_obs] + obs
            if "Acumular" in decision:
                df.loc[mask, col_he] = df.loc[mask, col_he] + 2.0
            if "Aprobado" in decision or "Justificado" in decision:
                df.loc[mask, col_atr] = 0
                if tipo_falta == "Justificada":
                    df.loc[mask, col_fj] = 1
                    df.loc[mask, col_fi] = 0
                else:
                    df.loc[mask, col_fj] = 0
                    df.loc[mask, col_fi] = 0
            elif tipo_falta == "Justificada":
                df.loc[mask, col_fj] = 1
                df.loc[mask, col_fi] = 0
                df.loc[mask, col_atr] = 0
            elif tipo_falta == "Injustificada":
                df.loc[mask, col_fj] = 0
                df.loc[mask, col_fi] = 1

    if canjes:
        df_canje = pd.DataFrame(canjes)
        for _, c in df_canje.iterrows():
            nombre = str(c.get('nombre', '')).strip()
            horas_usadas = float(c.get('horas_usadas', 0) or 0)
            mask_emp = df[col_nom].astype(str).str.strip() == nombre
            if mask_emp.any() and horas_usadas > 0:
                total_he = df.loc[mask_emp, col_he].sum()
                if total_he > 0:
                    factor = max(0.0, 1.0 - (horas_usadas / total_he))
                    df.loc[mask_emp, col_he] = df.loc[mask_emp, col_he] * factor
                df.loc[mask_emp, col_obs] = df.loc[mask_emp, col_obs] + f" | Canje {c.get('dias_canjeados', 0)}d"

    df.drop(columns=['_key'], inplace=True, errors='ignore')
    return df

st.set_page_config(page_title="Pre-Planilla Fridolin", page_icon="🏭", layout="wide")
st.title("🏭 Control de Asistencia y Reportes - Fridolin")

st.sidebar.image("https://em-content.zobj.net/source/apple/354/factory_1f3ed.png", width=80)
st.sidebar.title("Menú Principal")

usuario_actual = "Invitado"
rol_actual = "Jefe de Producción"
empleados_permitidos = []
pin_ok = True

try:
    df_emp_master = cached_load_sheet_data("01_Maestro_Empleados")
    if df_emp_master is not None and not df_emp_master.empty:
        usuario_actual, rol_actual, empleados_permitidos, pin_ok = render_user_selector(df_emp_master)
    else:
        st.sidebar.warning("No se pudo cargar el Maestro de Empleados.")
except Exception as e:
    st.sidebar.error(f"Error usuarios: {e}")

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
st.sidebar.caption("v2.19 - Filtro por CI")

if opcion == "📊 Parámetros y Reglas":
    st.header("⚙️ Parámetros y Reglas")
    data = [
        {"Parámetro": "Tolerancia Atraso", "Valor": "10 min", "Descripción": "Todo o Nada"},
        {"Parámetro": "Tiempo Comida", "Valor": "30 min", "Descripción": "Descuento 0.5h"},
        {"Parámetro": "Jornada Diurna", "Valor": "07:00-15:30", "Descripción": "8h = 1 turno"},
        {"Parámetro": "Jornada Nocturna", "Valor": "22:00-05:30", "Descripción": "7h = 1 turno"},
    ]
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

elif opcion == "⏱️ Importación Biométrico":
    st.header("⏱️ Importación Biométrico")
    df = cached_load_sheet_data("02_Importacion_Biometrico")
    if df is not None:
        st.success(f"{len(df)} registros")
        st.dataframe(df.head(20), use_container_width=True)
    else:
        st.warning("Sin datos")

elif opcion == "📝 Novedades y Permisos":
    st.header("📝 Novedades y Permisos")
    dict_nombre_ci = {}
    try:
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        if df_emp is not None and not df_emp.empty:
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

    todas = nov_mgr.obtener_todas_novedades()
    if todas:
        st.dataframe(pd.DataFrame(todas), use_container_width=True, hide_index=True)
    else:
        st.info("Sin novedades")

elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Panel de Aprobaciones")
    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        if df_bio is None or df_bio.empty:
            st.error("No se pudieron cargar marcaciones.")
            st.stop()

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

        if st.button("🔄 Cargar Excepciones", type="primary"):
            with st.spinner("Procesando solo tu personal (filtro CI)..."):
                df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
                df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                df_bio_p = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == periodo_sel].copy()

                # FILTRO POR CI
                cis_ok = obtener_cis_permitidos(df_emp, empleados_permitidos)
                df_bio_p = filtrar_bio_por_ci(df_bio_p, cis_ok, rol_actual)

                st.caption(f"Marcaciones filtradas: {len(df_bio_p)} | CIs permitidos: {len(cis_ok)}")

                if df_params is None or df_emp is None:
                    st.error("Faltan hojas.")
                else:
                    df_res = process_attendance(df_bio_p, df_params, None, df_emp, None)
                    df_exc = detect_exceptions(df_res)

                    if df_exc is not None and not df_exc.empty:
                        regs = db_mgr.obtener_regularizaciones_periodo(periodo_sel)
                        if regs:
                            df_reg = pd.DataFrame(regs)
                            col_nom = next((c for c in df_exc.columns if 'nombre' in str(c).lower()), None)
                            col_fec = next((c for c in df_exc.columns if 'fecha' in str(c).lower()), None)
                            if col_nom and col_fec:
                                df_exc = df_exc.copy()
                                df_exc['_key'] = df_exc[col_nom].astype(str).str.strip() + "_" + df_exc[col_fec].astype(str).str[:10]
                                keys_reg = set(df_reg['nombre'].astype(str).str.strip() + "_" + df_reg['fecha'].astype(str).str[:10])
                                df_exc = df_exc[~df_exc['_key'].isin(keys_reg)].copy()
                                df_exc.drop(columns=['_key'], inplace=True, errors='ignore')

                        decisiones = db_mgr.obtener_decisiones_periodo(periodo_sel)
                        if decisiones and not df_exc.empty:
                            df_dec = pd.DataFrame(decisiones)
                            col_ci = next((c for c in df_exc.columns if 'carnet' in str(c).lower() or str(c).upper() in ['ID','CI']), None)
                            col_fecha = next((c for c in df_exc.columns if 'fecha' in str(c).lower()), None)
                            if col_ci and col_fecha:
                                df_exc = df_exc.copy()
                                df_exc['_key'] = df_exc[col_ci].astype(str).str.strip() + "_" + df_exc[col_fecha].astype(str).str[:10]
                                df_dec['_key'] = df_dec['carnet_identidad'].astype(str).str.strip() + "_" + df_dec['fecha'].astype(str).str[:10]
                                keys_aprobados = set(df_dec[df_dec['decision'].astype(str).str.contains("Aprobado", case=False, na=False)]['_key'])
                                if "Tipo Excepción" in df_exc.columns:
                                    mask_falta = df_exc["Tipo Excepción"].astype(str).str.contains("Falta", case=False, na=False)
                                    df_exc = df_exc[~(mask_falta & df_exc['_key'].isin(keys_aprobados))].copy()
                                mapa_dec = dict(zip(df_dec['_key'], df_dec.get('decision', '')))
                                mapa_tf = dict(zip(df_dec['_key'], df_dec.get('tipo_falta', '')))
                                for col in df_exc.columns:
                                    if 'decisión' in str(col).lower() or 'decision' in str(col).lower():
                                        df_exc[col] = df_exc['_key'].map(mapa_dec).fillna(df_exc[col])
                                    if 'tipo falta' in str(col).lower():
                                        df_exc[col] = df_exc['_key'].map(mapa_tf).fillna(df_exc[col])
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
                    sel_tipo = st.selectbox("Filtrar Tipo:", tipos)
                with col_f2:
                    empleados = ["Todos"] + sorted([str(x) for x in df_exc.get("Nombre", pd.Series()).dropna().unique()])
                    sel_emp = st.selectbox("Filtrar Empleado:", empleados)

                df_fil = df_exc.copy()
                if sel_tipo != "Todos" and "Tipo Excepción" in df_fil.columns:
                    df_fil = df_fil[df_fil["Tipo Excepción"].astype(str) == sel_tipo]
                if sel_emp != "Todos" and "Nombre" in df_fil.columns:
                    df_fil = df_fil[df_fil["Nombre"].astype(str) == sel_emp]

                st.caption(f"{len(df_fil)} de {len(df_exc)} excepciones")

                with st.form("form_guardar_decisiones"):
                    col_decision = next((c for c in df_fil.columns if 'decisión' in str(c).lower() or 'decision' in str(c).lower()), None)
                    col_tipo_falta = next((c for c in df_fil.columns if 'tipo falta' in str(c).lower()), None)
                    column_config = {}
                    if col_decision:
                        column_config[col_decision] = st.column_config.SelectboxColumn("Decisión", options=["Pendiente", "Aprobado (Pago)", "Acumular (Próx. Mes)", "Rechazado", "Justificado", "Canjeado"])
                    if col_tipo_falta:
                        column_config[col_tipo_falta] = st.column_config.SelectboxColumn("Tipo Falta", options=["N/A", "Justificada", "Injustificada"])

                    df_edited = st.data_editor(df_fil, use_container_width=True, hide_index=True, disabled=not es_editable, column_config=column_config, key="editor_form")
                    submitted = st.form_submit_button("💾 Guardar Decisiones", type="primary", disabled=not es_editable)

                    if submitted:
                        col_ci = next((c for c in df_edited.columns if 'carnet' in str(c).lower() or str(c).upper() in ['ID','CI']), None)
                        col_nom = next((c for c in df_edited.columns if 'nombre' in str(c).lower()), None)
                        col_fec = next((c for c in df_edited.columns if 'fecha' in str(c).lower()), None)
                        col_tip = next((c for c in df_edited.columns if 'tipo excepción' in str(c).lower()), None)
                        col_dec = next((c for c in df_edited.columns if 'decisión' in str(c).lower() or 'decision' in str(c).lower()), None)
                        col_tf = next((c for c in df_edited.columns if 'tipo falta' in str(c).lower()), None)

                        if col_ci and col_fec:
                            guardadas = 0
                            for _, row in df_edited.iterrows():
                                ci_val = str(row.get(col_ci, "")).strip()
                                if not ci_val or ci_val.lower() in ['nan', 'none', '']:
                                    continue
                                decision_val = str(row.get(col_dec, "Pendiente")).strip() if col_dec else "Pendiente"
                                tipo_exc = str(row.get(col_tip, "")).strip() if col_tip else ""
                                data = {
                                    "periodo": periodo_sel,
                                    "carnet_identidad": ci_val,
                                    "nombre": str(row.get(col_nom, "")).strip() if col_nom else "",
                                    "fecha": str(row.get(col_fec, ""))[:10],
                                    "tipo_excepcion": tipo_exc,
                                    "decision": decision_val,
                                    "tipo_falta": str(row.get(col_tf, "N/A")).strip() if col_tf else "N/A",
                                    "observaciones": "",
                                    "registrado_por": usuario_actual
                                }
                                res = db_mgr.guardar_decision(data)
                                if res.get("exito"):
                                    guardadas += 1
                                    if "Falta" in tipo_exc and "Aprobado" in decision_val:
                                        data_reg = {
                                            "periodo": periodo_sel,
                                            "nombre": data["nombre"],
                                            "fecha": data["fecha"],
                                            "tipo": "Jornada Completa Omisa (Entrada + Salida)",
                                            "hora_entrada": "07:00:00",
                                            "hora_salida": "15:30:00",
                                            "motivo": "Aprobado (Método 1)",
                                            "registrado_por": usuario_actual
                                        }
                                        db_mgr.guardar_regularizacion(data_reg)
                            st.success(f"✅ {guardadas} decisiones guardadas.")
            else:
                st.success("No hay excepciones pendientes.")
        else:
            st.info("Haz clic en **Cargar Excepciones**.")

        st.divider()
        st.subheader("🛠️ Regularización")
        lista_empleados = empleados_permitidos if empleados_permitidos else []
        with st.form("form_regularizacion"):
            col1, col2 = st.columns(2)
            with col1:
                emp_reg = st.selectbox("Empleado*", options=lista_empleados if lista_empleados else ["(Sin)"])
                fecha_reg = st.date_input("Fecha*")
                tipo_reg = st.selectbox("Tipo*", ["Entrada Omisa", "Salida Omisa", "Jornada Completa Omisa (Entrada + Salida)"])
            with col2:
                hora_entrada = st.time_input("Hora Entrada", value=time(7, 0))
                hora_salida = st.time_input("Hora Salida", value=time(15, 30))
                motivo_reg = st.text_area("Motivo*")
            if st.form_submit_button("✅ Registrar", type="primary"):
                if not emp_reg or emp_reg == "(Sin)" or not motivo_reg:
                    st.warning("Complete los campos.")
                elif not es_editable:
                    st.error("Período debe estar EN_PROCESO.")
                else:
                    data_reg = {
                        "periodo": periodo_sel,
                        "nombre": emp_reg,
                        "fecha": str(fecha_reg),
                        "tipo": tipo_reg,
                        "hora_entrada": str(hora_entrada),
                        "hora_salida": str(hora_salida),
                        "motivo": motivo_reg,
                        "registrado_por": usuario_actual
                    }
                    res = db_mgr.guardar_regularizacion(data_reg)
                    if res.get("exito"):
                        st.success("✅ Regularización guardada.")
                    else:
                        st.error(res.get("mensaje"))

    except Exception as e:
        st.error(f"Error: {e}")

elif opcion == "🔄 Canje de Horas":
    st.header("🔄 Canje de Horas")
    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        if df_bio is None:
            st.error("Sin marcaciones.")
            st.stop()
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True) or [datetime.now().strftime('%Y-%m')]
        periodo_sel = st.selectbox("Período:", periodos, key="canje_periodo")

        decisiones = db_mgr.obtener_decisiones_periodo(periodo_sel)
        canjes_existentes = db_mgr.obtener_canjes_periodo(periodo_sel)

        if not decisiones:
            st.warning("No hay decisiones.")
        else:
            df_dec = pd.DataFrame(decisiones)
            df_acum = df_dec[df_dec['decision'].astype(str).str.contains("Acumular", case=False, na=False)].copy()
            if df_acum.empty:
                st.info("No hay horas para acumular.")
            else:
                st.dataframe(df_acum[["nombre", "fecha", "tipo_excepcion", "decision"]], use_container_width=True, hide_index=True)
                empleados_con_he = sorted(df_acum['nombre'].dropna().unique().tolist())
                emp_sel = st.selectbox("Empleado:", empleados_con_he)
                cant = len(df_acum[df_acum['nombre'] == emp_sel])
                st.info(f"**{emp_sel}** → {cant} registro(s)")
                dias_a_canjear = st.number_input("Días a canjear:", min_value=0.0, max_value=10.0, step=0.5, value=0.0)
                if st.button("💾 Guardar Canje", type="primary"):
                    if dias_a_canjear <= 0:
                        st.error("Indica al menos 0.5 días.")
                    else:
                        ci_val = str(df_acum[df_acum['nombre'] == emp_sel]['carnet_identidad'].iloc[0])
                        data = {
                            "periodo": periodo_sel,
                            "carnet_identidad": ci_val,
                            "nombre": emp_sel,
                            "dias_canjeados": float(dias_a_canjear),
                            "horas_usadas": float(dias_a_canjear * 8),
                            "faltas_afectadas": "",
                            "registrado_por": usuario_actual
                        }
                        res = db_mgr.guardar_canje(data)
                        if res.get("exito"):
                            st.success("✅ Canje guardado")
                            st.rerun()
                        else:
                            st.error(res.get("mensaje"))

        if canjes_existentes:
            st.dataframe(pd.DataFrame(canjes_existentes), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(str(e))

elif opcion == "💵 Valores Monetizados":
    st.header("💵 Valores Monetizados")
    st.info("Módulo de tarifas.")

elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("📑 Pre-Planilla")
    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        if df_bio is None:
            st.error("Sin marcaciones.")
            st.stop()

        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True) or [datetime.now().strftime('%Y-%m')]
        periodo_sel = st.selectbox("Período:", periodos, key="preplanilla_periodo")

        estado = lock_mgr.obtener_estado_periodo(periodo_sel, usuario=usuario_actual)
        st.info(f"**Estado:** {estado}")

        decisiones = db_mgr.obtener_decisiones_periodo(periodo_sel)
        regularizaciones = db_mgr.obtener_regularizaciones_periodo(periodo_sel)
        canjes = db_mgr.obtener_canjes_periodo(periodo_sel)

        col1, col2, col3 = st.columns(3)
        col1.metric("Decisiones", len(decisiones) if decisiones else 0)
        col2.metric("Regularizaciones", len(regularizaciones) if regularizaciones else 0)
        col3.metric("Canjes", len(canjes) if canjes else 0)

        st.divider()
        if st.button("📥 Generar Excel Oficial", type="primary"):
            with st.spinner("Procesando solo tu personal (filtro CI)..."):
                df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
                df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                df_bio_p = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == periodo_sel].copy()

                cis_ok = obtener_cis_permitidos(df_emp, empleados_permitidos)
                df_bio_p = filtrar_bio_por_ci(df_bio_p, cis_ok, rol_actual)

                if df_params is None or df_emp is None:
                    st.error("Faltan hojas.")
                else:
                    df_res = process_attendance(df_bio_p, df_params, None, df_emp, None)
                    df_res = aplicar_decisiones_a_asistencia(df_res, decisiones, regularizaciones, canjes)

                    datos_asistencia = df_res.to_dict('records') if df_res is not None and not df_res.empty else []
                    maestro = df_emp.to_dict('records') if df_emp is not None else []

                    nombre_archivo = f"PrePlanilla_Fridolin_{periodo_sel}_{usuario_actual.replace(' ', '_')}.xlsx"
                    resultado = ExcelExporter.exportar_preplanilla_oficial(
                        datos_asistencia=datos_asistencia,
                        maestro_empleados=maestro,
                        periodo=periodo_sel,
                        nombre_archivo=nombre_archivo
                    )

                    try:
                        with open(resultado, "rb") as f:
                            excel_bytes = f.read()
                        st.success(f"✅ Excel generado ({len(datos_asistencia)} registros).")
                        st.download_button(
                            label="⬇️ Descargar",
                            data=excel_bytes,
                            file_name=nombre_archivo,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    except Exception as e_file:
                        st.error(f"Error: {e_file}")

        if decisiones:
            with st.expander("Decisiones"):
                st.dataframe(pd.DataFrame(decisiones), use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Error: {e}")

elif opcion == "📜 Bitácora de Auditoría":
    st.header("📜 Bitácora")
    try:
        logs = audit_log.obtener_logs(200)
        if logs is not None and len(logs) > 0:
            st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
        else:
            st.info("Sin registros.")
    except Exception as e:
        st.error(f"Error: {e}")
        
