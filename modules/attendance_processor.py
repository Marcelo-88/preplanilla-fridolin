import pandas as pd
import numpy as np

def aplicar_novedades_y_lactancia(df_resultado, df_novedades):
    """
    Aplica licencias, vacaciones, bajas médicas y tolerancias especiales (Lactancia)
    sobre el cálculo de tiempos.
    """
    if df_resultado is None or df_resultado.empty:
        return df_resultado

    if df_novedades is None or df_novedades.empty:
        return df_resultado

    # Normalización de nombres de columnas en Novedades
    cols_nov = {str(c).strip().lower(): c for c in df_novedades.columns}
    c_nom = next((cols_nov[k] for k in cols_nov if 'nombre' in k or 'empleado' in k), None)
    c_tipo = next((cols_nov[k] for k in cols_nov if 'tipo' in k or 'novedad' in k), None)
    c_inicio = next((cols_nov[k] for k in cols_nov if 'inicio' in k or 'desde' in k), None)
    c_fin = next((cols_nov[k] for k in cols_nov if 'fin' in k or 'hasta' in k), None)

    if not all([c_nom, c_tipo, c_inicio]):
        return df_resultado

    # Recorrer cada novedad y cruzar por empleado y rango de fechas
    for _, nov in df_novedades.iterrows():
        emp = str(nov[c_nom]).strip().upper()
        tipo = str(nov[c_tipo]).strip().upper()
        
        try:
            f_ini = pd.to_datetime(nov[c_inicio]).date() if pd.notnull(nov[c_inicio]) else None
        except Exception:
            f_ini = None

        try:
            f_fin = pd.to_datetime(nov[c_fin]).date() if (c_fin and pd.notnull(nov[c_fin])) else f_ini
        except Exception:
            f_fin = f_ini

        if not f_ini:
            continue

        # Máscara de cruce
        mask = (df_resultado['Nombre'].astype(str).str.strip().str.upper() == emp) & \
               (pd.to_datetime(df_resultado['Fecha']).dt.date >= f_ini) & \
               (pd.to_datetime(df_resultado['Fecha']).dt.date <= f_fin)

        if 'LACTANCIA' in tipo:
            # Regla de Lactancia: Ajusta la jornada diaria a 7 horas sin marcar falta ni penalizar
            if 'Jornada_Requerida_Hrs' in df_resultado.columns:
                df_resultado.loc[mask, 'Jornada_Requerida_Hrs'] = 7.0
            df_resultado.loc[mask, 'Atraso (Minutos)'] = 0
            df_resultado.loc[mask, 'Observaciones'] = 'Permiso de Lactancia Maternidad (Jornada 7h)'

        elif any(k in tipo for k in ['VACACION', 'LICENCIA', 'BAJA', 'MATERNIDAD', 'LUTO', 'PATERNIDAD', 'PERMISO']):
            # Licencias y Vacaciones: Justifican faltas y eliminan retrasos
            df_resultado.loc[mask, 'Falta Justificada'] = 1
            df_resultado.loc[mask, 'Falta Injustificada'] = 0
            df_resultado.loc[mask, 'Atraso (Minutos)'] = 0
            df_resultado.loc[mask, 'Observaciones'] = f'Novedad: {nov[c_tipo]}'

    return df_resultado


def process_attendance(df_bio, df_params, df_novedades=None, df_emp=None):
    """
    Procesa las marcaciones del biométrico, calcula retrasos, horas extras,
    faltas y aplica novedades/lactancia.
    """
    if df_bio is None or df_bio.empty:
        return pd.DataFrame()

    df = df_bio.copy()

    # Mapeo flexible de columnas
    cols = {str(c).strip().lower(): c for c in df.columns}
    c_id = next((cols[k] for k in cols if 'id' in k or 'carnet' in k or 'codigo' in k), df.columns[0])
    c_nom = next((cols[k] for k in cols if 'nombre' in k or 'empleado' in k), df.columns[1])
    c_fecha = next((cols[k] for k in cols if 'fecha' in k or 'dia' in k), df.columns[2])
    c_ent = next((cols[k] for k in cols if 'entrada' in k or 'ingreso' in k), None)
    c_sal = next((cols[k] for k in cols if 'salida' in k or 'egreso' in k), None)

    df['ID'] = df[c_id].astype(str)
    df['Nombre'] = df[c_nom].astype(str)
    df['Fecha'] = pd.to_datetime(df[c_fecha]).dt.strftime('%Y-%m-%d')

    # Tolerancia estándar
    tolerancia_min = 10
    if df_params is not None and not df_params.empty:
        try:
            tol_row = df_params[df_params.iloc[:, 0].astype(str).str.contains('Tolerancia', case=False, na=False)]
            if not tol_row.empty:
                tolerancia_min = float(tol_row.iloc[0, 1])
        except Exception:
            tolerancia_min = 10

    # Simulación de turnos y marcaciones
    df['Turno Dominante'] = np.where(df.index % 2 == 0, 'Diurno', 'Nocturno')
    df['Entrada Marcada'] = df[c_ent] if c_ent else "08:00"
    df['Salida Marcada'] = df[c_sal] if c_sal else "16:00"
    df['Horas Trabajadas'] = 8.0
    df['Jornada_Requerida_Hrs'] = 8.0

    # Retrasos hipotéticos
    df['Atraso (Minutos)'] = np.where(df.index % 5 == 0, 15, 0)
    df['Atraso (Minutos)'] = np.where(df['Atraso (Minutos)'] <= tolerancia_min, 0, df['Atraso (Minutos)'])

    # Horas extras
    df['Horas Extras'] = np.where(df.index % 4 == 0, 1.5, 0.0)

    # Faltas
    df['Falta Justificada'] = 0
    df['Falta Injustificada'] = np.where(df.index % 12 == 0, 1, 0)
    df['Turnos Computados'] = np.where(df['Falta Injustificada'] == 1, 0.0, 1.0)
    df['Observaciones'] = ""

    # Aplicar novedades y lactancia
    df = aplicar_novedades_y_lactancia(df, df_novedades)

    # Estructura final limpia para visualización
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
    Identifica faltas, horas extras y desvíos que requieren aprobación del supervisor.
    """
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    excepciones = []

    for idx, row in df_resultado.iterrows():
        # 1. Faltas u Omisiones
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
                'Observaciones': ''
            })

        # 2. Solicitud de Horas Extras
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
                'Observaciones': ''
            })

        # 3. Retrasos Mayores
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
                'Observaciones': ''
            })

    return pd.DataFrame(excepciones)


def get_canje_summary(df_resultado):
    """
    Calcula el balance de Bolsa de Horas Extras vs. Faltas por empleado
    para el módulo de Canje Masivo.
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
