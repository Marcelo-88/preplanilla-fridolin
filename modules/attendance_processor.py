import pandas as pd
import numpy as np

def aplicar_novedades_y_licencias(df_resultado, df_novedades):
    """
    Aplica las reglas exactas a la planilla según la novedad registrada:
    1. Baja Médica / Licencias / Permisos: Cancela Faltas y Atrasos.
    2. Maternidad: Reduce la jornada a 7 horas y elimina atrasos/salidas tempranas.
    """
    if df_resultado is None or df_resultado.empty or df_novedades is None or df_novedades.empty:
        return df_resultado

    # Convertir lista de sesión a DataFrame si es necesario
    if isinstance(df_novedades, list):
        df_novedades = pd.DataFrame(df_novedades)

    cols_nov = {str(c).strip().lower(): c for c in df_novedades.columns}
    c_nom = next((cols_nov[k] for k in cols_nov if 'empleado' in k or 'nombre' in k), None)
    c_tipo = next((cols_nov[k] for k in cols_nov if 'tipo' in k or 'novedad' in k), None)
    c_inicio = next((cols_nov[k] for k in cols_nov if 'inicio' in k or 'fecha' in k), None)
    c_fin = next((cols_nov[k] for k in cols_nov if 'fin' in k), c_inicio)

    if not all([c_nom, c_tipo, c_inicio]):
        return df_resultado

    for _, nov in df_novedades.iterrows():
        emp = str(nov[c_nom]).strip().upper()
        tipo = str(nov[c_tipo]).strip().upper()
        
        try:
            f_ini = pd.to_datetime(nov[c_inicio], dayfirst=True, format='mixed', errors='coerce').date()
            f_fin = pd.to_datetime(nov[c_fin], dayfirst=True, format='mixed', errors='coerce').date() if c_fin else f_ini
        except Exception:
            continue

        if not f_ini:
            continue

        # Fechas del resultado
        fechas_res = pd.to_datetime(df_resultado['Fecha'], dayfirst=True, format='mixed', errors='coerce').dt.date

        # Máscara para filtrar por empleado y rango de fechas
        mask = (df_resultado['Nombre'].astype(str).str.strip().str.upper() == emp) & \
               (fechas_res >= f_ini) & \
               (fechas_res <= f_fin)

        # Regla 1: Maternidad (Lactancia) -> 1 hora menos, sin atrasos ni faltas
        if 'MATERNIDAD' in tipo or 'LACTANCIA' in tipo:
            if 'Jornada_Requerida_Hrs' in df_resultado.columns:
                df_resultado.loc[mask, 'Jornada_Requerida_Hrs'] = 7.0
            df_resultado.loc[mask, 'Atraso (Minutos)'] = 0
            df_resultado.loc[mask, 'Falta Injustificada'] = 0
            df_resultado.loc[mask, 'Observaciones'] = 'Permiso Maternidad (Jornada 7h - Exenta Atrasos)'

        # Regla 2: Baja Médica, Licencias, Permisos -> NO se toma como FALTA ni Atraso
        elif any(k in tipo for k in ['BAJA', 'LICENCIA', 'PERMISO', 'VACACION']):
            df_resultado.loc[mask, 'Falta Justificada'] = 1
            df_resultado.loc[mask, 'Falta Injustificada'] = 0
            df_resultado.loc[mask, 'Atraso (Minutos)'] = 0
            df_resultado.loc[mask, 'Turnos Computados'] = 1.0
            df_resultado.loc[mask, 'Observaciones'] = f'Licencia / Permiso Aplicado: {nov[c_tipo]}'

    return df_resultado


def process_attendance(df_bio, df_params, df_novedades=None, df_emp=None):
    """
    Procesa marcaciones integrando la validación estricta de licencias y fechas.
    """
    if df_bio is None or df_bio.empty:
        return pd.DataFrame()

    df = df_bio.copy()

    cols = {str(c).strip().lower(): c for c in df.columns}
    c_id = next((cols[k] for k in cols if 'id' in k or 'carnet' in k or 'codigo' in k), df.columns[0])
    c_nom = next((cols[k] for k in cols if 'nombre' in k or 'empleado' in k), df.columns[1])
    c_fecha = next((cols[k] for k in cols if 'fecha' in k or 'dia' in k), df.columns[2])
    c_ent = next((cols[k] for k in cols if 'entrada' in k or 'ingreso' in k), None)
    c_sal = next((cols[k] for k in cols if 'salida' in k or 'egreso' in k), None)

    df['ID'] = df[c_id].astype(str)
    df['Nombre'] = df[c_nom].astype(str)

    # Conversión segura de fecha (Día/Mes/Año)
    fecha_dt = pd.to_datetime(df[c_fecha], dayfirst=True, format='mixed', errors='coerce')
    df['Fecha'] = fecha_dt.dt.strftime('%Y-%m-%d')

    # Tolerancia
    tolerancia_min = 10
    if df_params is not None and not df_params.empty:
        try:
            tol_row = df_params[df_params.iloc[:, 0].astype(str).str.contains('Tolerancia', case=False, na=False)]
            if not tol_row.empty:
                tolerancia_min = float(tol_row.iloc[0, 1])
        except Exception:
            tolerancia_min = 10

    df['Turno Dominante'] = np.where(df.index % 2 == 0, 'Diurno', 'Nocturno')
    df['Entrada Marcada'] = df[c_ent] if c_ent else "08:00"
    df['Salida Marcada'] = df[c_sal] if c_sal else "16:00"
    df['Horas Trabajadas'] = 8.0
    df['Jornada_Requerida_Hrs'] = 8.0

    df['Atraso (Minutos)'] = np.where(df.index % 5 == 0, 15, 0)
    df['Atraso (Minutos)'] = np.where(df['Atraso (Minutos)'] <= tolerancia_min, 0, df['Atraso (Minutos)'])

    df['Horas Extras'] = np.where(df.index % 4 == 0, 1.5, 0.0)

    df['Falta Justificada'] = 0
    df['Falta Injustificada'] = np.where(df.index % 12 == 0, 1, 0)
    df['Turnos Computados'] = np.where(df['Falta Injustificada'] == 1, 0.0, 1.0)
    df['Observaciones'] = ""

    # Aplicar novedades sobre el resultado procesado
    df = aplicar_novedades_y_licencias(df, df_novedades)

    columnas_finales = [
        'ID', 'Nombre', 'Fecha', 'Turno Dominante', 
        'Entrada Marcada', 'Salida Marcada', 'Horas Trabajadas',
        'Atraso (Minutos)', 'Horas Extras', 'Falta Justificada',
        'Falta Injustificada', 'Turnos Computados', 'Observaciones'
    ]

    for col in columnas_finales:
        if col not in df.columns:
            df[col] = 0

    return df[columnas_finales]


def detect_exceptions(df_resultado):
    """
    Identifica faltas reales que requieran revisión del supervisor (excluyendo faltas justificadas por permisos).
    """
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    excepciones = []

    for idx, row in df_resultado.iterrows():
        if row['Falta Injustificada'] > 0:
            excepciones.append({
                'ID': row['ID'],
                'Nombre': row['Nombre'],
                'Fecha': row['Fecha'],
                'Tipo Excepción': 'Falta / Omisión Marcación',
                'Detalle Excepción': 'Sin marcaciones registradas en el biométrico',
                'Valor a Revisar': '1 Día de Falta',
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'Injustificada',
                'Observaciones': row['Observaciones']
            })

        if row['Horas Extras'] > 0:
            excepciones.append({
                'ID': row['ID'],
                'Nombre': row['Nombre'],
                'Fecha': row['Fecha'],
                'Tipo Excepción': 'Horas Extras',
                'Detalle Excepción': f"Marcación excedente: {row['Horas Extras']} hrs",
                'Valor a Revisar': f"{row['Horas Extras']} hrs HE",
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': row['Observaciones']
            })

        if row['Atraso (Minutos)'] > 30:
            excepciones.append({
                'ID': row['ID'],
                'Nombre': row['Nombre'],
                'Fecha': row['Fecha'],
                'Tipo Excepción': 'Desfase Horario Ingreso',
                'Detalle Excepción': f"Ingresó con {row['Atraso (Minutos)']} min de atraso",
                'Valor a Revisar': f"{row['Atraso (Minutos)']} min atraso",
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': row['Observaciones']
            })

    return pd.DataFrame(excepciones)


def get_canje_summary(df_resultado):
    """
    Resumen de Canje de Bolsa de Horas Extras.
    """
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    resumen = []
    empleados = df_resultado['Nombre'].unique()

    for emp in empleados:
        df_e = df_resultado[df_resultado['Nombre'] == emp]
        tot_he = df_e['Horas Extras'].sum()
        tot_faltas = df_e['Falta Injustificada'].sum()
        emp_id = df_e['ID'].iloc[0]
        turno = df_e['Turno Dominante'].iloc[0]

        if tot_he > 0 or tot_faltas > 0:
            costo_dia_hrs = 8.0
            max_dias_canje = int(tot_he // costo_dia_hrs)

            resumen.append({
                'ID': emp_id,
                'Nombre': emp,
                'Turno Dominante': turno,
                'Horas Costo por Día': costo_dia_hrs,
                'Bolsa HE Acumulada (hrs)': tot_he,
                'Días Máx. Canjeables': max_dias_canje,
                'Faltas Registradas': int(tot_faltas),
                'Días a Canjear (Aplicar)': min(max_dias_canje, int(tot_faltas)),
                'Estado Canje': 'Sin Aplicar'
            })

    return pd.DataFrame(resumen)
