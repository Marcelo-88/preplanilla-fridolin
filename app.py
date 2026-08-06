import streamlit as st
import pandas as pd

# Módulos del Sistema
from modules.data_loader import load_google_sheet_data
from modules.auth_permissions import verify_pin, filter_dataframe_by_supervisor
from modules.attendance_processor import process_attendance
from modules.novedades import init_novedades_db, add_novedad, get_novedades, delete_novedad
from modules.lock_manager import init_lock_db, get_period_status, set_period_status
from modules.excel_exporter import export_preplanilla_excel
from modules.audit_logger import init_audit_db, log_action

# Configuración Inicial de Página
st.set_page_config(
    page_title="Control de Tiempos - Fridolin",
    page_icon="⏱️",
    layout="wide"
)

# Inicializar Base de Datos SQLite locales
init_novedades_db()
init_lock_db()
init_audit_db()

# Título Principal
st.title("Planilla de Control de Tiempos")

# --- SIDEBAR DE AUTENTICACIÓN Y NAVEGACIÓN ---
st.sidebar.header("Credenciales de Supervisor")

# Carga de Supervisores desde Google Sheets
@st.cache_data(ttl=300)
def fetch_supervisores():
    return load_google_sheet_data("Supervisores")

df_supervisores = fetch_supervisores()

supervisor_nombre = None
rol_supervisor = None

if not df_supervisores.empty and 'Nombre' in df_supervisores.columns:
    lista_supervisores = df_supervisores['Nombre'].dropna().tolist()
    supervisor_nombre = st.sidebar.selectbox("Seleccione su Nombre:", options=lista_supervisores)
    
    pin_ingresado = st.sidebar.text_input("Ingrese su PIN (4 dígitos):", type="password")
    
    if pin_ingresado:
        es_valido, rol = verify_pin(supervisor_nombre, pin_ingresado, df_supervisores)
        if es_valido:
            st.sidebar.success("🔑 PIN Correcto")
            st.sidebar.info(f"👑 Rol: {rol}")
            rol_supervisor = rol
        else:
            st.sidebar.error("❌ PIN Incorrecto")
            st.stop()
    else:
        st.info("Por favor ingrese su PIN de acceso para continuar.")
        st.stop()
else:
    st.error("No se pudo cargar la lista de supervisores desde Google Sheets.")
    st.stop()

# Menú de Navegación entre Vistas
st.sidebar.markdown("---")
vista_seleccionada = st.sidebar.radio(
    "Seleccione una vista:",
    [
        "📊 Parámetros y Reglas",
        "👤 Maestro de Empleados",
        "⏰ Importación Biométrico",
        "📝 Novedades y Permisos",
        "✅ Aprobaciones Supervisores",
        "📑 Pre-Planilla y Reportes"
    ]
)

# --- CARGA GENERAL DE DATOS BASE ---
@st.cache_data(ttl=180)
def fetch_all_base_data():
    emp = load_google_sheet_data("Empleados")
    bio = load_google_sheet_data("Biometrico")
    return emp, bio

df_empleados, df_biometrico = fetch_all_base_data()

# Filtrar datos de empleados por asignación del supervisor actual
df_emp_filtrado = filter_dataframe_by_supervisor(df_empleados, supervisor_nombre, rol_supervisor)

# Carga de Novedades desde SQLite
df_novedades = get_novedades()

# --- PROCESAMIENTO DINÁMICO DE ASISTENCIA ---
df_procesado, df_excepciones, df_resumen = process_attendance(
    df_biometrico,
    df_emp_filtrado,
    df_novedades
)

# --- RENDERING DE VISTAS ---

# 1. PARÁMETROS Y REGLAS
if vista_seleccionada == "📊 Parámetros y Reglas":
    st.subheader("Parámetros y Reglas del Sistema")
    st.write("Configuración activa de tolerancias, turnos y reglas de cálculo de horas extra.")
    col1, col2, col3 = st.columns(3)
    col1.metric("Tolerancia Atraso", "15 Mins")
    col2.metric("Jornada Estándar", "8 Horas")
    col3.metric("Días Laborales / Semana", "6 Días")

# 2. MAESTRO DE EMPLEADOS
elif vista_seleccionada == "👤 Maestro de Empleados":
    st.subheader("Maestro de Empleados Asignados")
    st.dataframe(df_emp_filtrado, use_container_width=True)

# 3. IMPORTACIÓN BIOMÉTRICO
elif vista_seleccionada == "⏰ Importación Biométrico":
    st.subheader("Registros Crudos del Biométrico")
    st.dataframe(df_biometrico, use_container_width=True)

# 4. NOVEDADES Y PERMISOS
elif vista_seleccionada == "📝 Novedades y Permisos":
    st.subheader("Gestión de Novedades, Licencias y Permisos")
    
    st.markdown("### Registrar Nueva Novedad")
    with st.form("form_novedad", clear_on_submit=True):
        col_emp, col_tipo = st.columns(2)
        
        emp_options = df_emp_filtrado['Nombre'].tolist() if 'Nombre' in df_emp_filtrado.columns else []
        emp_sel = col_emp.selectbox("Empleado:", options=emp_options)
        tipo_nov = col_tipo.selectbox("Tipo de Novedad:", ["Permiso", "Licencia Médica", "Vacación", "Lactancia", "Suspensión"])
        
        col_f1, col_f2 = st.columns(2)
        f_inicio = col_f1.date_input("Fecha Inicio:")
        f_fin = col_f2.date_input("Fecha Fin:")
        obs = st.text_input("Observación / Justificación:")
        
        btn_guardar = st.form_submit_button("Guardar Novedad")
        
        if btn_guardar:
            # Buscar ID del empleado seleccionado
            emp_id_found = ""
            if 'ID' in df_emp_filtrado.columns:
                match = df_emp_filtrado[df_emp_filtrado['Nombre'] == emp_sel]
                if not match.empty:
                    emp_id_found = str(match['ID'].iloc[0])

            add_novedad(emp_id_found, emp_sel, tipo_nov, str(f_inicio), str(f_fin), obs, supervisor_nombre)
            log_action(supervisor_nombre, "REGISTRO_NOVEDAD", f"Novedad {tipo_nov} para {emp_sel} ({f_inicio} a {f_fin})")
            st.success("✅ Novedad registrada con éxito. Se actualizarán las excepciones automáticamente.")
            st.rerun()

    st.markdown("---")
    st.markdown("### Histórico de Novedades Registradas")
    if not df_novedades.empty:
        st.dataframe(df_novedades, use_container_width=True)
    else:
        st.info("No hay novedades registradas en el sistema.")

# 5. APROBACIONES SUPERVISORES (EXCEPCIONES)
elif vista_seleccionada == "✅ Aprobaciones Supervisores":
    st.subheader("Módulo de Aprobaciones y Control de Excepciones")
    
    if not df_excepciones.empty:
        st.warning(f"Se han detectado {len(df_excepciones)} excepciones pendientes de revisión.")
        st.dataframe(df_excepciones, use_container_width=True)
    else:
        st.success("🎉 No existen excepciones o faltas pendientes de revisión para sus empleados asignados.")

# 6. PRE-PLANILLA Y REPORTES
elif vista_seleccionada == "📑 Pre-Planilla y Reportes":
    st.subheader("Pre-Planilla Consolidada de Control de Tiempos")
    
    if not df_procesado.empty:
        # Métricas principales
        total_reg = len(df_procesado)
        tot_hrs = df_procesado['Horas Trabajadas'].sum()
        tot_atrasos = df_procesado['Atraso (Minutos)'].sum()
        tot_he = df_procesado['Horas Extras 50%'].sum() + df_procesado['Horas Extras 100%'].sum()
        tot_fj = df_procesado['Falta Justificada'].sum()
        tot_fij = df_procesado['Falta Injustificada'].sum()
        tot_turnos = df_procesado['Turnos Completados'].sum()

        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
        m1.metric("Registros", total_reg)
        m2.metric("Horas Trab.", f"{tot_hrs:.1f}")
        m3.metric("Atrasos Min", f"{tot_atrasos}")
        m4.metric("Horas Extras", f"{tot_he:.1f}")
        m5.metric("Faltas Just.", f"{tot_fj}")
        m6.metric("Faltas Injust.", f"{tot_fij}")
        m7.metric("Turnos Comp.", f"{tot_turnos:.1f}")

        st.markdown("---")
        st.dataframe(df_procesado, use_container_width=True)

        # Exportación a Excel
        st.markdown("---")
        excel_data = export_preplanilla_excel(df_procesado, df_resumen)
        st.download_button(
            label="📥 Descargar Reporte Consolidado (Excel)",
            data=excel_data,
            file_name="Preplanilla_Control_Tiempos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No hay registros para mostrar en el período actual.")
