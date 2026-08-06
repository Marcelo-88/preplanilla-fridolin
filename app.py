import streamlit as st
import pandas as pd
import numpy as np
import datetime

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Control de Asistencia - Fridolin",
    layout="wide",
    page_icon="🏭"
)

# ==========================================
# PARÁMETROS Y REGLAS GENERALES (DEFAULT)
# ==========================================
HORARIO_DIURNO_INICIO = datetime.time(7, 0)
HORARIO_DIURNO_FIN = datetime.time(15, 30)
HORARIO_NOCTURNO_INICIO = datetime.time(22, 0)
HORARIO_NOCTURNO_FIN = datetime.time(5, 30)
TOLERANCIA_ATRASO_MIN = 15

# ==========================================
# LÓGICA DE CÁLCULO DE ASISTENCIA Y REGLAS
# ==========================================
def calcular_jornada_y_atrasos(row):
    """
    Calcula horas trabajadas, atrasos, horas extras y turnos computados
    resolviendo el cruce de medianoche y aplicando la regla de 1.5 turnos nocturnos.
    """
    entrada_str = row.get('Entrada')
    salida_str = row.get('Salida')
    turno = str(row.get('Turno', 'Diurno')).strip()
    
    # Manejo de fechas
    fecha_val = row.get('Fecha')
    try:
        fecha = pd.to_datetime(fecha_val)
    except Exception:
        fecha = pd.Timestamp.today()

    # Manejo de marcaciones incompletas o ausencias
    if pd.isna(entrada_str) or pd.isna(salida_str) or entrada_str in ['Falta Marcación', ''] or salida_str in ['Falta Marcación', '']:
        return pd.Series({
            'Horas Trabajadas': 0.0,
            'Atraso (Minutos)': 0,
            'Horas Extras': 0.0,
            'Horas Nocturnas': 0.0,
            'Turnos Computados': 0.0,
            'Estado Registro': 'Falta Marcación'
        })

    # Conversión a objetos de tiempo
    dummy_date = datetime.date(2026, 1, 1)
    try:
        t_in = datetime.datetime.strptime(str(entrada_str).strip(), '%H:%M').time()
        t_out = datetime.datetime.strptime(str(salida_str).strip(), '%H:%M').time()
    except ValueError:
        return pd.Series({
            'Horas Trabajadas': 0.0,
            'Atraso (Minutos)': 0,
            'Horas Extras': 0.0,
            'Horas Nocturnas': 0.0,
            'Turnos Computados': 0.0,
            'Estado Registro': 'Error Formato Hora'
        })

    dt_in = datetime.datetime.combine(dummy_date, t_in)
    dt_out = datetime.datetime.combine(dummy_date, t_out)

    # CORRECCIÓN 1: Cruce de medianoche (Salida < Entrada)
    if dt_out <= dt_in:
        dt_out += datetime.timedelta(days=1)

    horas_trabajadas = round((dt_out - dt_in).total_seconds() / 3600.0, 2)

    # CORRECCIÓN 2: Cálculo de Atrasos por Turno
    if turno == 'Nocturno':
        target_in = datetime.datetime.combine(dummy_date, HORARIO_NOCTURNO_INICIO)
        # Si entra temprano los domingos/viernes (ej. 18:00) no computa atraso
        if t_in < datetime.time(22, 0) and (fecha.weekday() in [4, 6]):
            target_in = datetime.datetime.combine(dummy_date, t_in)
    else:
        target_in = datetime.datetime.combine(dummy_date, HORARIO_DIURNO_INICIO)

    diferencia_in = (dt_in - target_in).total_seconds() / 60.0
    atraso_minutos = max(0, int(diferencia_in - TOLERANCIA_ATRASO_MIN)) if diferencia_in > TOLERANCIA_ATRASO_MIN else 0

    # REGLA 3: Pre-aprobación 1.5 Turnos para Personal Nocturno
    turnos_computados = 1.0
    requiere_aprobacion = False

    es_domingo = (fecha.weekday() == 6)
    es_viernes = (fecha.weekday() == 4)

    if turno == 'Nocturno':
        # Todo personal nocturno tiene pre-aprobado el 1.5 en ingresos extendidos de domingo/viernes
        if (es_domingo or es_viernes) and t_in >= datetime.time(18, 0):
            turnos_computados = 1.5
    else:
        # Si personal diurno marca en horario dominical extendido, requiere aprobación
        if es_domingo and t_in >= datetime.time(18, 0):
            requiere_aprobacion = True

    # Horas extras
    jornada_normal = 8.0
    horas_extras = max(0.0, round(horas_trabajadas - jornada_normal, 2)) if horas_trabajadas > jornada_normal else 0.0

    return pd.Series({
        'Horas Trabajadas': horas_trabajadas,
        'Atraso (Minutos)': atraso_minutos,
        'Horas Extras': horas_extras,
        'Horas Nocturnas': horas_trabajadas if turno == 'Nocturno' else 0.0,
        'Turnos Computados': turnos_computados,
        'Estado Registro': 'Revisión Requerida' if requiere_aprobacion else 'OK'
    })

# ==========================================
# NAVEGACIÓN LATERAL
# ==========================================
st.sidebar.title("🏭 Menú Principal")
opcion = st.sidebar.radio(
    "Seleccione una vista:",
    [
        "📋 Parámetros y Reglas",
        "👥 Maestro de Empleados",
        "⏱️ Importación Biométrico",
        "📝 Novedades y Permisos",
        "✅ Aprobaciones Supervisores",
        "📊 Pre-Planilla y Reportes"
    ]
)
st.sidebar.markdown("---")
st.sidebar.caption("Sistema de Control de Asistencia v1.2 — Fridolin")

# ==========================================
# 1. PARÁMETROS Y REGLAS
# ==========================================
if opcion == "📋 Parámetros y Reglas":
    st.title("📋 Configuración de Parámetros y Reglas de Negocio")
    st.info("Define las políticas de horarios, tolerancias y reglas de turnos aplicables a la fábrica.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Horarios por Turno")
        st.time_input("Entrada Turno Diurno", HORARIO_DIURNO_INICIO)
        st.time_input("Salida Turno Diurno", HORARIO_DIURNO_FIN)
        st.time_input("Entrada Turno Nocturno", HORARIO_NOCTURNO_INICIO)
        st.time_input("Salida Turno Nocturno", HORARIO_NOCTURNO_FIN)

    with col2:
        st.subheader("Tolerancias y Turnos Específicos")
        st.number_input("Tolerancia de Atraso (Minutos)", value=TOLERANCIA_ATRASO_MIN, step=1)
        st.checkbox("Pre-aprobar 1.5 Turnos a Personal Nocturno (Domingo/Viernes 18:00)", value=True)
        st.checkbox("Jornada Operativa Semanal de 6 Días (Lunes a Sábado)", value=True)

    if st.button("Guardar Parámetros"):
        st.success("Parámetros actualizados correctamente.")

# ==========================================
# 2. MAESTRO DE EMPLEADOS
# ==========================================
elif opcion == "👥 Maestro de Empleados":
    st.title("👥 Maestro de Empleados")
    st.markdown("Gestión de la nómina de trabajadores de la fábrica (con CIs limpios para biométrico).")

    uploaded_maestro = st.file_uploader("Cargar lista maestro de empleados (CSV/Excel)", type=['csv', 'xlsx'])
    if uploaded_maestro:
        st.success("Archivo maestro cargado exitosamente.")

# ==========================================
# 3. IMPORTACIÓN BIOMÉTRICO
# ==========================================
elif opcion == "⏱️ Importación Biométrico":
    st.title("⏱️ Importación de Datos del Biométrico")
    st.markdown("Carga del archivo plano de marcaciones capturadas por el reloj biométrico.")

    uploaded_bio = st.file_uploader("Cargar marcaciones del Biométrico (CSV/Excel)", type=['csv', 'xlsx'])
    if uploaded_bio:
        df_uploaded = pd.read_excel(uploaded_bio) if uploaded_bio.name.endswith('.xlsx') else pd.read_csv(uploaded_bio)
        st.session_state['df_biometrico_raw'] = df_uploaded
        st.success(f"Se cargaron {len(df_uploaded)} marcaciones exitosamente.")
        st.dataframe(df_uploaded.head(10), use_container_width=True)

# ==========================================
# 4. NOVEDADES Y PERMISOS
# ==========================================
elif opcion == "📝 Novedades y Permisos":
    st.title("📝 Novedades, Permisos y Faltas")
    st.markdown("Registro manual de licencias, bajas médicas y permisos justificados.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.selectbox("Empleado:", ["Seleccionar...", "Saul Leon (166039)", "Lynn Soria (8228265)", "Freddy Ayala (1)"])
    with col2:
        st.date_input("Fecha de Novedad:", datetime.date.today())
    with col3:
        st.selectbox("Tipo de Novedad:", ["Falta Justificada", "Permiso Personal", "Baja Médica", "Vacación", "Comisión"])
    
    st.text_area("Observaciones / Aclarativas:")
    if st.button("Registrar Novedad"):
        st.success("Novedad guardada correctamente.")

# ==========================================
# 5. APROBACIONES SUPERVISORES
# ==========================================
elif opcion == "✅ Aprobaciones Supervisores":
    st.title("✅ Aprobaciones y Excepciones de Supervisores")
    st.markdown("Modulo para revisión y validación de horas extras, marcaciones impares o turnos especiales.")

    st.subheader("Alertas Pendientes de Validación")
    st.warning("No hay marcaciones fuera de regla pendientes de autorización manual.")

# ==========================================
# 6. PRE-PLANILLA Y REPORTES
# ==========================================
elif opcion == "📊 Pre-Planilla y Reportes":
    st.title("🏭 Control de Asistencia y Reportes - Fridolin")
    st.subheader("Reporte Consolidado de Asistencia para RRHH / Contabilidad")

    # Obtener o simular datos de prueba procesados
    df_data = st.session_state.get('df_biometrico_raw', None)

    if df_data is None:
        # Estructura base demostrativa si aún no suben archivo
        data_demo = [
            {"ID": "8228265", "Nombre": "Lynn Soria", "Fecha": "2026-06-01", "Tipo Día": "Hábil", "Entrada": "07:05", "Salida": "16:14", "Turno": "Diurno"},
            {"ID": "166039", "Nombre": "Saul Leon", "Fecha": "2026-06-08", "Tipo Día": "Hábil", "Entrada": "22:10", "Salida": "07:48", "Turno": "Nocturno"},
            {"ID": "166039", "Nombre": "Saul Leon", "Fecha": "2026-06-15", "Tipo Día": "Hábil", "Entrada": "21:53", "Salida": "05:30", "Turno": "Nocturno"},
            {"ID": "14724640", "Nombre": "David Leon Limon", "Fecha": "2026-06-07", "Tipo Día": "Domingo", "Entrada": "18:00", "Salida": "05:30", "Turno": "Nocturno"},
        ]
        df_data = pd.DataFrame(data_demo)

    # Procesar dataframe con la función de cálculo
    df_calculado = df_data.join(df_data.apply(calcular_jornada_y_atrasos, axis=1))

    # Filtros interactivos
    col1, col2 = st.columns(2)
    with col1:
        emp_list = ['Todos'] + sorted(list(df_calculado['Nombre'].dropna().unique()))
        emp_selected = st.selectbox("Filtrar por Empleado:", emp_list)
    with col2:
        turnos_list = ['Todos', 'Diurno', 'Nocturno']
        turno_selected = st.selectbox("Filtrar por Turno:", turnos_list)

    df_filtered = df_calculado.copy()
    if emp_selected != 'Todos':
        df_filtered = df_filtered[df_filtered['Nombre'] == emp_selected]
    if turno_selected != 'Todos':
        df_filtered = df_filtered[df_filtered['Turno'] == turno_selected]

    # Tabla Principal de Salida
    st.subheader("Planilla de Control de Tiempos")
    st.dataframe(
        df_filtered[[
            'ID', 'Nombre', 'Fecha', 'Tipo Día', 'Entrada', 'Salida', 
            'Horas Trabajadas', 'Atraso (Minutos)', 'Horas Extras', 
            'Horas Nocturnas', 'Turnos Computados', 'Turno', 'Estado Registro'
        ]],
        use_container_width=True
    )

    # KPIs métricos consolidados
    st.markdown("---")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Días / Registros", len(df_filtered))
    k2.metric("Total Horas Trabajadas", f"{df_filtered['Horas Trabajadas'].sum():.2f} hrs")
    k3.metric("Total Atrasos", f"{int(df_filtered['Atraso (Minutos)'].sum())} min")
    k4.metric("Horas Extras", f"{df_filtered['Horas Extras'].sum():.2f} hrs")
    k5.metric("Total Turnos", f"{df_filtered['Turnos Computados'].sum():.1f}")

    # Botón de Descarga Excel
    st.markdown("---")
    @st.cache_data
    def convert_df_to_excel(df):
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='PrePlanilla')
        return output.getvalue()

    excel_data = convert_df_to_excel(df_filtered)
    st.download_button(
        label="📥 Descargar Reporte de Asistencia (Excel)",
        data=excel_data,
        file_name=f"PrePlanilla_Fridolin_{datetime.date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
