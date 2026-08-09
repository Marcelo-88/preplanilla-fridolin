import streamlit as st
import pandas as pd
from datetime import datetime, time
import re

from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions
from modules.auth_permissions import render_user_selector, filter_dataframe_by_supervisor

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
st.sidebar.caption("v2.10 - Pre-Planilla básica")

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

# 4. APROBACIONES
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
            with st.spinner("Procesando..."):
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

                if df_exc is not None and not df_exc.empty:
                    # Filtrar regularizaciones
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

                    # Decisiones + Método 1
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

                with st.form("form_guardar_decisiones"):
                    col_decision = next((c for c in df_fil.columns if 'decisión' in str(c).lower() or 'decision' in str(c).lower()), None)
                    col_tipo_falta = next((c for c in df_fil.columns if 'tipo falta' in str(c).lower()), None)

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
                        column_config=column_config,
                        key="editor_form"
                    )

                    submitted = st.form_submit_button("💾 Guardar Decisiones", type="primary", disabled=not es_editable)

                    if submitted:
                        st.write("⏳ Procesando...")
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
                                            "motivo": "Aprobado automáticamente (Método 1)",
                                            "registrado_por": usuario_actual
                                        }
                                        db_mgr.guardar_regularizacion(data_reg)

                            st.success(f"✅ {guardadas} decisiones guardadas.")
                            st.info("Si aprobaste faltas, vuelve a Cargar Excepciones.")
            else:
                st.success("No hay excepciones pendientes.")
        else:
            st.info("Haz clic en **Cargar Excepciones del Período**.")

        # Regularización Método 2
        st.divider()
        st.subheader("🛠️ Regularización de Marcaciones Faltantes")
        lista_empleados = empleados_permitidos if empleados_permitidos else []
        if not lista_empleados:
            try:
                df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                col_nom = next((c for c in df_emp.columns if 'nombre' in str(c).lower()), None)
                if col_nom:
                    lista_empleados = sorted(df_emp[col_nom].astype(str).str.strip().unique().tolist())
            except:
                pass

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

            if st.form_submit_button("✅ Registrar Regularización", type="primary"):
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
                    audit_log.registrar_evento(usuario_actual, usuario_actual, "REGULARIZACION_OMISION", "Aprobaciones", data_reg)
                    if res.get("exito"):
                        st.success(f"✅ Regularización guardada para {emp_reg}.")
                        st.info("Vuelve a Cargar Excepciones.")
                    else:
                        st.error(res.get("mensaje"))

    except Exception as e:
        st.error(f"Error: {e}")

# 5. CANJE
elif opcion == "🔄 Canje de Horas":
    st.header("🔄 Canje de Horas Extras por Faltas")

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True) or [datetime.now().strftime('%Y-%m')]
        periodo_sel = st.selectbox("Período:", periodos, key="canje_periodo")

        decisiones = db_mgr.obtener_decisiones_periodo(periodo_sel)
        canjes_existentes = db_mgr.obtener_canjes_periodo(periodo_sel)

        if not decisiones:
            st.warning("No hay decisiones guardadas.")
        else:
            df_dec = pd.DataFrame(decisiones)
            df_acum = df_dec[df_dec['decision'].astype(str).str.contains("Acumular", case=False, na=False)].copy()

            if df_acum.empty:
                st.info("No hay horas marcadas como “Acumular (Próx. Mes)”.")
            else:
                st.subheader("Detalle de horas acumuladas")
                st.dataframe(df_acum[["nombre", "fecha", "tipo_excepcion", "decision"]], use_container_width=True, hide_index=True)

                resumen = df_acum.groupby("nombre").size().reset_index(name="Registros Acumulados")
                st.subheader("Resumen por empleado")
                st.dataframe(resumen, use_container_width=True, hide_index=True)

                st.divider()
                empleados_con_he = sorted(df_acum['nombre'].dropna().unique().tolist())
                emp_sel = st.selectbox("Empleado a canjear:", empleados_con_he)
                cant = len(df_acum[df_acum['nombre'] == emp_sel])
                st.info(f"**{emp_sel}** tiene {cant} registro(s) acumulado(s).")

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
                            st.success(f"✅ Canje guardado para {emp_sel}")
                            st.rerun()
                        else:
                            st.error(res.get("mensaje"))

        st.divider()
        st.subheader("Canjes realizados")
        if canjes_existentes:
            st.dataframe(pd.DataFrame(canjes_existentes), use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay canjes.")

    except Exception as e:
        st.error(str(e))

# 6. VALORES
elif opcion == "💵 Valores Monetizados":
    st.header("💵 Valores Monetizados")
    st.info("Módulo de tarifas.")

# 7. PRE-PLANILLA (NUEVA)
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("📑 Pre-Planilla Consolidada")
    st.caption("Resumen de decisiones, regularizaciones y canjes del período")

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True) or [datetime.now().strftime('%Y-%m')]
        periodo_sel = st.selectbox("Período:", periodos, key="preplanilla_periodo")

        # Cargar datos
        decisiones = db_mgr.obtener_decisiones_periodo(periodo_sel)
        regularizaciones = db_mgr.obtener_regularizaciones_periodo(periodo_sel)
        canjes = db_mgr.obtener_canjes_periodo(periodo_sel)
        novedades = nov_mgr.obtener_todas_novedades()

        # Filtrar novedades del período (aproximado por fecha)
        if novedades:
            df_nov = pd.DataFrame(novedades)
            # Filtro simple por mes si hay fechas
            if 'fecha_inicio' in df_nov.columns:
                df_nov = df_nov[df_nov['fecha_inicio'].astype(str).str.startswith(periodo_sel)]
        else:
            df_nov = pd.DataFrame()

        st.subheader(f"Resumen del período {periodo_sel}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Decisiones guardadas", len(decisiones) if decisiones else 0)
        col2.metric("Regularizaciones", len(regularizaciones) if regularizaciones else 0)
        col3.metric("Canjes", len(canjes) if canjes else 0)
        col4.metric("Novedades", len(df_nov) if not df_nov.empty else 0)

        st.divider()

        # Decisiones
        st.subheader("1. Decisiones del Supervisor")
        if decisiones:
            st.dataframe(pd.DataFrame(decisiones), use_container_width=True, hide_index=True)
        else:
            st.info("Sin decisiones registradas.")

        # Regularizaciones
        st.subheader("2. Regularizaciones de Marcaciones")
        if regularizaciones:
            st.dataframe(pd.DataFrame(regularizaciones), use_container_width=True, hide_index=True)
        else:
            st.info("Sin regularizaciones.")

        # Canjes
        st.subheader("3. Canjes de Horas Extras")
        if canjes:
            st.dataframe(pd.DataFrame(canjes), use_container_width=True, hide_index=True)
        else:
            st.info("Sin canjes.")

        # Novedades del período
        st.subheader("4. Novedades del Período")
        if not df_nov.empty:
            st.dataframe(df_nov, use_container_width=True, hide_index=True)
        else:
            st.info("Sin novedades en este período.")

        st.divider()
        st.success("Esta es la base de la Pre-Planilla. Los datos ya están consolidados y listos para exportación o revisión final.")

    except Exception as e:
        st.error(f"Error: {e}")

# 8. BITÁCORA
elif opcion == "📜 Bitácora de Auditoría":
    st.header("📜 Bitácora de Auditoría")
    try:
        logs = audit_log.obtener_logs(300)
        if logs is not None and len(logs) > 0:
            st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
        else:
            st.info("Sin registros.")
    except Exception as e:
        st.error(f"Error: {e}")
