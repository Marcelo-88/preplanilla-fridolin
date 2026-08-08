import streamlit as st
import pandas as pd
import io
import os
import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, Optional

# --- IMPORTS DE MÓDULOS DEL PROYECTO ---
from modules.data_loader import load_sheet_data
from modules.attendance_processor import process_attendance, detect_exceptions, get_canje_summary
from modules.auth_permissions import render_user_selector, filter_dataframe_by_supervisor
from modules.excel_exporter import ExcelExporter
from modules.lock_manager import LockManager
from modules.audit_logger import AuditLogger
from modules.tarifas_manager import (
    cargar_tarifas, guardar_tarifas, actualizar_excepcion_empleado, eliminar_excepcion_empleado
)


# Fallback Gestor Novedades
try:
    from modules.novedades import NovedadesManager
except ImportError:
    class NovedadesManager:
        def __init__(self, json_path: str = "novedades_local.json"):
            self.json_path = json_path

        def obtener_tipos_novedad(self):
            return ["Baja Médica", "Licencia por Paternidad", "Licencia por Luto", "Vacación", "Lactancia Maternidad", "Permiso Personal"]

        def obtener_todas_novedades(self):
            if os.path.exists(self.json_path):
                try:
                    with open(self.json_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    return []
            return []

        def registrar_novedad(self, empleado_id, empleado_nombre, tipo_novedad, fecha_inicio, fecha_fin, justificacion, registrado_por_pin):
            novs = self.obtener_todas_novedades()
            nueva = {
                "ID": empleado_id,
                "Nombre_Completo": empleado_nombre,
                "Tipo_Novedad": tipo_novedad,
                "Fecha_Inicio": fecha_inicio,
                "Fecha_Fin": fecha_fin,
                "Justificacion": justificacion,
                "Registrado_Por": registrado_por_pin,
                "Fecha_Registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            novs.append(nueva)
            try:
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump(novs, f, ensure_ascii=False, indent=2)
                return {"exito": True, "mensaje": "Novedad registrada exitosamente."}
            except Exception as e:
                return {"exito": False, "mensaje": f"Error guardando novedad: {e}"}


# --- INICIALIZACIÓN DE GESTORES ---
@st.cache_resource
def get_managers():
    audit = AuditLogger()
    lock = LockManager()
    nov = NovedadesManager()
    return audit, lock, nov

audit_log, lock_mgr, nov_mgr = get_managers()

if not hasattr(lock_mgr, "exportar_respaldo_json"):
    st.cache_resource.clear()
    audit_log, lock_mgr, nov_mgr = get_managers()

# Caching de Funciones
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
    page_icon="🥐",
    layout="wide"
)

st.title("🥐 Control de Asistencia y Pre-Planilla - Fridolin")

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

opciones_menu = [
    "📊 Parámetros y Reglas",
    "👥 Maestro de Empleados",
    "⏱️ Importación Biométrico",
    "📝 Novedades y Permisos",
    "✅ Aprobaciones Supervisores",
    "💵 Valores Monetizados (Punto 3)",
    "📑 Pre-Planilla y Reportes",
    "📜 Bitácora de Auditoría"
]

opcion = st.sidebar.radio("Seleccione una vista:", opciones_menu)

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
        {"Parámetro / Regla": "Alerta_7mo_Dia", "Valor": "7 días", "Descripción y Aplicación": "Genera alerta automática si un trabajador registra marcaciones los 7 días de una misma semana."}
    ]

    df_reglas = pd.DataFrame(data_reglas)
    st.dataframe(df_reglas, use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------------
# 2. MAESTRO DE EMPLEADOS
# -----------------------------------------------------------------------------
elif opcion == "👥 Maestro de Empleados":
    st.header("Maestro de Empleados")
    try:
        df_emp = cached_load_sheet_data("01_Maestro_Empleados")
        cols_sin_pin = [col for col in df_emp.columns if str(col).strip().upper() != "PIN"]
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
    tab_ver_nov, tab_crear_nov = st.tabs(["📋 Novedades Registradas", "➕ Registrar Nueva Novedad"])

    with tab_ver_nov:
        try:
            df_nov_sheet = cached_load_sheet_data("04_Novedades_y_Permisos")
        except Exception:
            df_nov_sheet = pd.DataFrame()

        df_nov_local = pd.DataFrame(nov_mgr.obtener_todas_novedades())
        df_nov_comb = pd.concat([df_nov_sheet, df_nov_local], ignore_index=True) if not df_nov_local.empty else df_nov_sheet
        st.dataframe(df_nov_comb, use_container_width=True, hide_index=True)

    with tab_crear_nov:
        if not pin_ok:
            st.warning("🔒 Requiere ingresar su PIN de Supervisor en la barra lateral.")
        else:
            with st.form("form_nueva_novedad"):
                df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                col_nombre = 'Nombre_Completo' if 'Nombre_Completo' in df_emp.columns else 'Nombre'
                df_emp_fil = filter_dataframe_by_supervisor(df_emp, col_nombre, empleados_permitidos, rol_actual)
                lista_emps = df_emp_fil[col_nombre].dropna().unique().tolist() if col_nombre in df_emp_fil else []

                emp_seleccionado = st.selectbox("Seleccione Empleado:*", options=sorted(lista_emps))
                tipo_nov = st.selectbox("Tipo de Novedad / Licencia:*", options=nov_mgr.obtener_tipos_novedad())
                
                col_f1, col_f2 = st.columns(2)
                fecha_ini = col_f1.date_input("Fecha Inicio:*")
                fecha_fin = col_f2.date_input("Fecha Fin:*")
                justificacion_txt = st.text_area("Justificación / Certificado Médico:*")

                if st.form_submit_button("✅ Guardar Novedad"):
                    res_reg = nov_mgr.registrar_novedad(
                        empleado_id="EMP-000",
                        empleado_nombre=emp_seleccionado,
                        tipo_novedad=tipo_nov,
                        fecha_inicio=fecha_ini.strftime("%Y-%m-%d"),
                        fecha_fin=fecha_fin.strftime("%Y-%m-%d"),
                        justificacion=justificacion_txt,
                        registrado_por_pin=usuario_actual
                    )
                    if res_reg["exito"]:
                        audit_log.registrar_evento(usuario_actual, usuario_actual, "REGISTRO_NOVEDAD", "Novedades", {"empleado": emp_seleccionado, "tipo": tipo_nov})
                        st.success(res_reg["mensaje"])
                        st.rerun()


# -----------------------------------------------------------------------------
# 5. APROBACIONES SUPERVISORES
# -----------------------------------------------------------------------------
elif opcion == "✅ Aprobaciones Supervisores":
    st.header("✅ Centro de Aprobaciones y Excepciones")
    if not pin_ok:
        st.warning("🔒 Ingrese su PIN de 4 dígitos en la barra lateral para desbloquear el módulo.")
        st.stop()

    try:
        df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
        df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
        periodos_disponibles = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True)
    except Exception:
        periodos_disponibles = [datetime.now().strftime('%Y-%m')]

    col_p1, col_p2 = st.columns([2, 2])
    periodo_sel = col_p1.selectbox("🗓️ Seleccionar Período de Revisión:", options=periodos_disponibles)
    estado_periodo = lock_mgr.obtener_estado_periodo(periodo_sel, usuario=usuario_actual)
    es_editable = lock_mgr.es_editable(periodo_sel, rol_actual, usuario=usuario_actual)

    with col_p2:
        st.subheader(f"Estado Período ({usuario_actual}): **{estado_periodo}**")

    col_rev1, col_rev2, col_rev3 = st.columns(3)
    if col_rev1.button("▶️ Marcar EN PROCESO"):
        lock_mgr.cambiar_estado(periodo_sel, lock_mgr.ESTADO_EN_PROCESO, usuario_actual, rol_actual, usuario_nombre=usuario_actual)
        st.rerun()
    if col_rev2.button("🔒 FINALIZAR y Cerrar Período"):
        lock_mgr.cambiar_estado(periodo_sel, lock_mgr.ESTADO_FINALIZADO, usuario_actual, rol_actual, usuario_nombre=usuario_actual)
        st.rerun()


# -----------------------------------------------------------------------------
# 6. VALORES MONETIZADOS (PUNTO 3 - NUEVA VISTA)
# -----------------------------------------------------------------------------
elif opcion == "💵 Valores Monetizados (Punto 3)":
    st.header("💵 Gestión de Valores Monetizados y Tarifas de Jornaleros")
    st.caption("Módulo exclusivo para Superusuarios. Permite configurar y aprobar tarifas de jornaleros.")

    # Verificación de Rol
    roles_super = ["RESPONSABLE_OPERACIONES", "JEFE_PRODUCCION", "Jefe de Producción", "ADMINISTRADOR", "Superusuario"]
    if rol_actual not in roles_super:
        st.error("⛔ Acceso denegado: Esta pantalla requiere privilegios de Superusuario.")
        st.stop()

    config = cargar_tarifas()

    st.subheader("1. Tarifas Base Globales (Aplica al 90% del Personal)")
    col1, col2 = st.columns(2)

    with col1:
        diurno_norm = st.number_input("Diurno Normal 8h [Bs]", value=float(config["tarifas_base"].get("diurno_normal_8h", 100.0)), step=5.0)
        diurno_15 = st.number_input("Diurno 1.5 / 12h [Bs]", value=float(config["tarifas_base"].get("diurno_1_5_12h", 150.0)), step=5.0)

    with col2:
        nocturno_norm = st.number_input("Nocturno Normal 8h [Bs]", value=float(config["tarifas_base"].get("nocturno_normal_8h", 120.0)), step=5.0)
        nocturno_15 = st.number_input("Nocturno 1.5 / 12h [Bs]", value=float(config["tarifas_base"].get("nocturno_1_5_12h", 180.0)), step=5.0)

    if st.button("💾 Guardar Tarifas Base", type="primary"):
        config["tarifas_base"] = {
            "diurno_normal_8h": diurno_norm,
            "diurno_1_5_12h": diurno_15,
            "nocturno_normal_8h": nocturno_norm,
            "nocturno_1_5_12h": nocturno_15
        }
        if guardar_tarifas(config):
            audit_log.registrar_evento(usuario_actual, usuario_actual, "ACTUALIZAR_TARIFAS_BASE", "Tarifas", config["tarifas_base"])
            st.success("✅ Tarifas base guardadas exitosamente en config_tarifas.json")

    st.divider()

    st.subheader("2. Excepciones Tarifarias por Empleado")
    c_ci, c_tipo, c_monto = st.columns([2, 3, 2])
    ci_in = c_ci.text_input("Carnet de Identidad (CI)")
    tipo_in = c_tipo.selectbox("Tipo de Turno", [
        ("diurno_normal_8h", "Diurno Normal (8h)"),
        ("diurno_1_5_12h", "Diurno 1.5 (12h)"),
        ("nocturno_normal_8h", "Nocturno Normal (8h)"),
        ("nocturno_1_5_12h", "Nocturno 1.5 (12h)")
    ], format_func=lambda x: x[1])
    monto_in = c_monto.number_input("Monto Personalizado [Bs]", min_value=0.0, step=5.0)

    if st.button("➕ Registrar / Actualizar Excepción"):
        if ci_in.strip():
            actualizar_excepcion_empleado(ci_in.strip(), tipo_in[0], monto_in)
            audit_log.registrar_evento(usuario_actual, usuario_actual, "EXCEPCION_TARIFA", "Tarifas", {"CI": ci_in, "tipo": tipo_in[0], "monto": monto_in})
            st.success(f"Excepción asignada correctamente a CI: {ci_in}")
            st.rerun()
        else:
            st.warning("Ingrese un CI válido.")

    excepciones = config.get("excepciones", {})
    if excepciones:
        st.write("**Excepciones Registradas Actuales:**")
        list_e = []
        for ci, t_dict in excepciones.items():
            for t_type, m in t_dict.items():
                list_e.append({"Carnet_Identidad": ci, "Tipo_Turno": t_type, "Monto_Excepcion_Bs": m})
        st.dataframe(pd.DataFrame(list_e), use_container_width=True)

        ci_del = st.selectbox("Seleccionar CI para borrar excepciones:", list(excepciones.keys()))
        if st.button("🗑️ Eliminar Excepción"):
            eliminar_excepcion_empleado(ci_del)
            st.info(f"Excepciones eliminadas para {ci_del}")
            st.rerun()


# -----------------------------------------------------------------------------
# 7. PRE-PLANILLA Y REPORTES
# -----------------------------------------------------------------------------
elif opcion == "📑 Pre-Planilla y Reportes":
    st.header("Reporte Consolidado de Asistencia y Pre-Planilla Oficial")
    
    with st.spinner("Procesando marcaciones y tiempos..."):
        try:
            df_bio = cached_load_sheet_data("02_Importacion_Biometrico")
            df_params = cached_load_sheet_data("05_Parametros_y_Reglas")
            df_emp = cached_load_sheet_data("01_Maestro_Empleados")
                
            df_bio['dt_temp'] = pd.to_datetime(df_bio.iloc[:, 2], dayfirst=True, errors='coerce')
            periodos_rep = sorted(df_bio['dt_temp'].dt.strftime('%Y-%m').dropna().unique().tolist(), reverse=True)
            
            p_sel_rep = st.selectbox("🗓️ Filtrar Período de Reporte:", options=periodos_rep if periodos_rep else ["2026-08"])
            df_bio_rep = df_bio[df_bio['dt_temp'].dt.strftime('%Y-%m') == p_sel_rep].copy() if 'dt_temp' in df_bio.columns else df_bio

            df_resultado = run_cached_attendance_processing(df_bio_rep, df_params, df_emp, nov_mgr)

            if df_resultado is not None and not df_resultado.empty:
                st.subheader("Planilla General de Control de Tiempos")
                st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                
                st.divider()
                st.subheader("📥 Exportaciones Disponibles")

                c_exp1, c_exp2 = st.columns(2)

                with c_exp1:
                    archivo_oficial = f"PrePlanilla_Oficial_3Pestanas_{p_sel_rep}.xlsx"
                    ExcelExporter.exportar_preplanilla_oficial(
                        datos_asistencia=df_resultado.to_dict('records'),
                        maestro_empleados=df_emp.to_dict('records') if not df_emp.empty else [],
                        periodo=p_sel_rep,
                        nombre_archivo=archivo_oficial
                    )
                    with open(archivo_oficial, "rb") as f:
                        st.download_button(
                            label="⭐ Descargar Excel Pre-Planilla Oficial (3 Pestañas)",
                            data=f,
                            file_name=archivo_oficial,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )

                with c_exp2:
                    archivo_simple = f"PrePlanilla_Simple_{p_sel_rep}.xlsx"
                    ExcelExporter.exportar_preplanilla(df_resultado.to_dict('records'), p_sel_rep, archivo_simple)
                    with open(archivo_simple, "rb") as f:
                        st.download_button(
                            label="📥 Descargar Reporte Consolidado Simple",
                            data=f,
                            file_name=archivo_simple,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
        except Exception as e:
            st.error(f"Error durante el procesamiento del reporte: {e}")


# -----------------------------------------------------------------------------
# 8. BITÁCORA DE AUDITORÍA
# -----------------------------------------------------------------------------
elif opcion == "📜 Bitácora de Auditoría":
    st.header("📜 Bitácora de Auditoría e Historial de Cambios")
    df_logs = audit_log.obtener_logs(limite=1000)

    if not df_logs.empty:
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Aún no existen registros en la bitácora de auditoría.")
