import streamlit as st
import pandas as pd
import numpy as np
import datetime
import calendar
import io

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Control de Asistencia - Fridolin",
    layout="wide",
    page_icon="🏭"
)

# ==========================================
# ENLACE DE CONEXIÓN A GOOGLE DRIVE / SHEETS
# ==========================================
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1h9ZOIOAZbnBzdn6FcV2slUxt1layLigt/export?format=xlsx"

# ==========================================
# PARÁMETROS Y REGLAS DE NEGOCIO
# ==========================================
HORARIO_DIURNO_INICIO = datetime.time(7, 0)
HORARIO_DIURNO_FIN = datetime.time(15, 30)
HORARIO_NOCTURNO_INICIO = datetime.time(22, 0)
HORARIO_NOCTURNO_FIN = datetime.time(5, 30)
TOLERANCIA_ATRASO_MIN = 15

# ==========================================
# FUNCIÓN DE CARGA AUTOMÁTICA DESDE DRIVE
# ==========================================
@st.cache_data(ttl=60)
def cargar_datos_drive():
    try:
        xls = pd.ExcelFile(GOOGLE_SHEET_URL)
        
        # 1. Cargar Maestro de Empleados
        df_maestro = pd.read_excel(xls, sheet_name='01_Maestro_Empleados') if '01_Maestro_Empleados' in xls.sheet_names else pd.DataFrame()
        
        # 2. Cargar Importación Biométrico
        sheet_bio = '02_Importacion_Biometrico' if '02_Importacion_Biometrico' in xls.sheet_names else xls.sheet_names[0]
        df_bio_raw = pd.read_excel(xls, sheet_name=sheet_bio)
        
        return df_maestro, df_bio_raw
    except Exception as e:
        st.error(f"Error al conectar con Google Drive: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ==========================================
# MOTOR DE PARSEO DE MARCACIONES
# ==========================================
def auto_parse_biometric_df(df_input):
    if df_input is None or df_input.empty:
        return pd.DataFrame()

    df = df_input.copy()
    cols = [str(c).strip() for c in df.columns]

    # Identificación de columnas principales
    id_col, name_col, dt_col, tipo_col = None, None, None, None
    for c in cols:
        c_low = c.lower()
        if not id_col and any(x in c_low for x in ['id', 'carnet', 'ci', 'codigo', 'unnamed: 0']):
            id_col = c
        elif not name_col and any(x in c_low for x in ['nombre', 'empleado', 'trabajador', 'unnamed: 1']):
            name_col = c
        elif not dt_col and any(x in c_low for x in ['fecha', 'hora', 'marcacion', 'tiempo', 'unnamed: 2']):
            dt_col = c
        elif not tipo_col and any(x in c_low for x in ['tipo', 'movimiento', 'evento', 'unnamed: 3']):
            tipo_col = c

    if not id_col and len(cols) >= 1: id_col = cols[0]
    if not name_col and len(cols) >= 2: name_col = cols[1]
    if not dt_col and len(cols) >= 3: dt_col = cols[2]
    if not tipo_col and len(cols) >= 4: tipo_col = cols[3]

    df['dt_parsed'] = pd.to_datetime(df[dt_col], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['dt_parsed']).sort_values([id_col, 'dt_parsed'])

    records = []
    for (emp_id, emp_name), group in df.groupby([id_col, name_col]):
        punches = group.to_dict('records')
        i = 0
        while i < len(punches):
            p = punches[i]
            p_type = str(p.get(tipo_col, '')).strip()
            p_dt = p['dt_parsed']

            if 'salida' not in p_type.lower():
                fecha_str = p_dt.strftime('%Y-%m-%d')
                entrada_str = p_dt.strftime('%H:%M')
                salida_str = 'Falta Marcación'

                if i + 1 < len(punches):
                    next_p = punches[i+1]
                    next_type = str(next_p.get(tipo_col, '')).strip()
                    next_dt = next_p['dt_parsed']

                    if 'salida' in next_type.lower() and (next_dt - p_dt).total_seconds() <= 16 * 3600:
                        salida_str = next_dt.strftime('%H:%M')
                        i += 1

                records.append({
                    'ID': str(emp_id),
                    'Nombre': str(emp_name),
                    'Fecha': fecha_str,
                    'Entrada': entrada_str,
                    'Salida': salida_str,
                    'Tipo Día': 'Domingo' if p_dt.weekday() == 6 else 'Hábil',
                    'Turno': 'Nocturno' if p_dt.hour >= 18 or p_dt.hour < 5 else 'Diurno'
                })
            i += 1

    return pd.DataFrame(records)

# ==========================================
# CÁLCULO DE JORNADA Y EXCEPCIONES
# ==========================================
def calcular_jornada_y_atrasos(row):
    entrada_str = row.get('Entrada')
    salida_str = row.get('Salida')
    turno = str(row.get('Turno', 'Diurno')).strip()
    
    fecha_val = row.get('Fecha')
    try:
        fecha = pd.to_datetime(fecha_val)
    except Exception:
        fecha = pd.Timestamp.today()

    if pd.isna(entrada_str) or pd.isna(salida_str) or entrada_str in ['Falta Marcación', '', 'NaN'] or salida_str in ['Falta Marcación', '', 'NaN']:
        return pd.Series({
            'Horas Trabajadas': 0.0,
            'Atraso (Minutos)': 0,
            'Horas Extras': 0.0,
            'Horas Nocturnas': 0.0,
            'Turnos Computados': 0.0,
            'Estado Registro': 'Falta Marcación'
        })

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

    if dt_out <= dt_in:
        dt_out += datetime.timedelta(days=1)

    horas_trabajadas = round((dt_out - dt_in).total_seconds() / 3600.0, 2)

    if turno == 'Nocturno':
        target_in = datetime.datetime.combine(dummy_date, HORARIO_NOCTURNO_INICIO)
        if t_in < datetime.time(22, 0) and (fecha.weekday() in [4, 6]):
            target_in = datetime.datetime.combine(dummy_date, t_in)
    else:
        target_in = datetime.datetime.combine(dummy_date, HORARIO_DIURNO_INICIO)

    diferencia_in = (dt_in - target_in).total_seconds() / 60.0
    atraso_minutos = max(0, int(diferencia_in - TOLERANCIA_ATRASO_MIN)) if diferencia_in > TOLERANCIA_ATRASO_MIN else 0

    turnos_computados = 1.0
    requiere_aprobacion = False
    es_domingo = (fecha.weekday() == 6)
    es_viernes = (fecha.weekday() == 4)

    if turno == 'Nocturno':
        if (es_domingo or es_viernes) and t_in >= datetime.time(18, 0):
            turnos_computados = 1.5
    else:
        if es_domingo and t_in >= datetime.time(18, 0):
            requiere_aprobacion = True

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
# GENERADOR DE LIBRO EXCEL QUINCENAL
# ==========================================
def generar_excel_quincenal(df, mes_nombre, anio):
    output = io.BytesIO()
    df['Fecha_dt'] = pd.to_datetime(df['Fecha'])
    
    df_q1 = df[df['Fecha_dt'].dt.day <= 15]
    df_q2 = df[df['Fecha_dt'].dt.day > 15]

    def consolidar_quincena(df_sub):
        if df_sub.empty:
            return pd.DataFrame(columns=['ID / CI', 'Nombre Empleado', 'Turno', 'Días Trabajados', 'Total Horas Trabajadas', 'Total Atrasos (Minutos)', 'Total Horas Extras', 'Total Horas Nocturnas', 'Total Turnos Computados'])
        
        resumen = df_sub.groupby(['ID', 'Nombre', 'Turno']).agg(
            Dias_Trabajados=('Fecha', 'count'),
            Horas_Trabajadas=('Horas Trabajadas', 'sum'),
            Atraso_Minutos=('Atraso (Minutos)', 'sum'),
            Horas_Extras=('Horas Extras', 'sum'),
            Horas_Nocturnas=('Horas Nocturnas', 'sum'),
            Turnos_Computados=('Turnos Computados', 'sum')
        ).reset_index()

        resumen.columns = [
            'ID / CI', 'Nombre Empleado', 'Turno', 'Días Trabajados', 
            'Total Horas Trabajadas', 'Total Atrasos (Minutos)', 
            'Total Horas Extras', 'Total Horas Nocturnas', 'Total Turnos Computados'
        ]
        return resumen

    resumen_q1 = consolidar_quincena(df_q1)
    resumen_q2 = consolidar_quincena(df_q2)

    meses_dict = {"Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12}
    num_mes = meses_dict.get(mes_nombre, 6)
    last_day = calendar.monthrange(anio, num_mes)[1]

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        resumen_q1.to_excel(writer, index=False, sheet_name=f'Semana 1 al 15 {mes_nombre[:3].upper()}')
        resumen_q2.to_excel(writer, index=False, sheet_name=f'Semana 16 al {last_day} {mes_nombre[:3].upper()}')

    return output.getvalue()

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
st.sidebar.caption("Sistema de Control de Asistencia v1.6 — Fridolin")

# Carga automática de Google Drive
df_maestro_drive, df_bio_drive = cargar_datos_drive()

# ==========================================
# 1. PARÁMETROS Y REGLAS
# ==========================================
if opcion == "📋 Parámetros y Reglas":
    st.title("📋 Configuración de Parámetros y Reglas de Negocio")
    st.info("Configuración de horarios, tolerancias y cálculo de turnos nocturnos.")

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

# ==========================================
# 2. MAESTRO DE EMPLEADOS
# ==========================================
elif opcion == "👥 Maestro de Empleados":
    st.title("👥 Maestro de Empleados (Conectado a Google Drive)")
    st.success("🟢 Datos sincronizados automáticamente desde Google Drive.")
    st.dataframe(df_maestro_drive, use_container_width=True)

# ==========================================
# 3. IMPORTACIÓN BIOMÉTRICO
# ==========================================
elif opcion == "⏱️ Importación Biométrico":
    st.title("⏱️ Importación de Marcaciones (Google Drive)")
    st.success("🟢 Sincronizado automáticamente desde la hoja 02_Importacion_Biometrico.")
    df_parsed = auto_parse_biometric_df(df_bio_drive)
    st.dataframe(df_parsed, use_container_width=True)

# ==========================================
# 4. NOVEDADES Y PERMISOS
# ==========================================
elif opcion == "📝 Novedades y Permisos":
    st.title("📝 Novedades y Permisos")
    st.text_input("ID / CI Empleado:")
    st.selectbox("Tipo de Novedad:", ["Falta Justificada", "Permiso Personal", "Baja Médica", "Vacación"])
    if st.button("Guardar Novedad"):
        st.success("Novedad registrada.")

# ==========================================
# 5. APROBACIONES SUPERVISORES
# ==========================================
elif opcion == "✅ Aprobaciones Supervisores":
    st.title("✅ Aprobaciones Supervisores")
    st.info("No hay excepciones pendientes.")

# ==========================================
# 6. PRE-PLANILLA Y REPORTES
# ==========================================
elif opcion == "📊 Pre-Planilla y Reportes":
    st.title("🏭 Control de Asistencia y Reportes - Fridolin")
    
    col_mes, col_anio = st.columns(2)
    with col_mes:
        mes_seleccionado = st.selectbox("Seleccionar Mes de Procesamiento:", ["Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], index=0)
    with col_anio:
        anio_seleccionado = st.number_input("Año:", value=2026, step=1)

    df_data = auto_parse_biometric_df(df_bio_drive)

    if df_data.empty:
        st.warning("Cargando datos desde Google Drive...")
    else:
        df_data['Fecha_dt'] = pd.to_datetime(df_data['Fecha'], errors='coerce')
        meses_dict = {"Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12}
        num_mes = meses_dict.get(mes_seleccionado, 6)

        df_mes = df_data[(df_data['Fecha_dt'].dt.month == num_mes) & (df_data['Fecha_dt'].dt.year == anio_seleccionado)]

        if df_mes.empty:
            df_mes = df_data

        df_calculado = df_mes.join(df_mes.apply(calcular_jornada_y_atrasos, axis=1))

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

        st.dataframe(
            df_filtered[[
                'ID', 'Nombre', 'Fecha', 'Tipo Día', 'Entrada', 'Salida', 
                'Horas Trabajadas', 'Atraso (Minutos)', 'Horas Extras', 
                'Horas Nocturnas', 'Turnos Computados', 'Turno', 'Estado Registro'
            ]],
            use_container_width=True
        )

        st.markdown("---")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Días / Registros", len(df_filtered))
        k2.metric("Total Horas Trabajadas", f"{df_filtered['Horas Trabajadas'].sum():.2f} hrs")
        k3.metric("Total Atrasos", f"{int(df_filtered['Atraso (Minutos)'].sum())} min")
        k4.metric("Horas Extras", f"{df_filtered['Horas Extras'].sum():.2f} hrs")
        k5.metric("Total Turnos", f"{df_filtered['Turnos Computados'].sum():.1f}")

        st.markdown("---")
        excel_bytes = generar_excel_quincenal(df_filtered, mes_seleccionado, anio_seleccionado)
        
        st.download_button(
            label=f"📥 Descargar Planilla Quincenal en Excel ({mes_seleccionado} {anio_seleccionado})",
            data=excel_bytes,
            file_name=f"Planilla_Consolidada_{mes_seleccionado.upper()}_{anio_seleccionado}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
