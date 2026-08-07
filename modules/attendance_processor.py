import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time

def process_attendance(df_bio, df_params=None, df_nov=None, df_emp=None, _nov_mgr=None):
    """
    Procesa las marcaciones biométricas considerando turnos diurnos y nocturnos
    que cruzan la medianoche (Entrada Día N, Salida Día N+1).
    """
    if df_bio is None or df_bio.empty:
        return _empty_attendance_df()

    df = df_bio.copy()

    # 1. Normalización de columnas de fecha/hora
    if 'FechaHora' not in df.columns:
        if 'Fecha' in df.columns and 'Hora' in df.columns:
            df['FechaHora'] = pd.to_datetime(df['Fecha'].astype(str) + ' ' + df['Hora'].astype(str), errors='coerce')
        elif 'Fecha' in df.columns:
            df['FechaHora'] = pd.to_datetime(df['Fecha'], errors='coerce')
        else:
            return _empty_attendance_df()
    else:
        df['FechaHora'] = pd.to_datetime(df['FechaHora'], errors='coerce')

    df = df.dropna(subset=['FechaHora']).sort_values(by=['Carnet_Identidad', 'FechaHora']).reset_index(drop=True)

    # Limpieza de duplicados o marcaciones hiper-cercanas (< 2 minutos)
    df['Prev_Carnet'] = df['Carnet_Identidad'].shift(1)
    df['Prev_Time'] = df['FechaHora'].shift(1)
    df['Diff_Min'] = (df['FechaHora'] - df['Prev_Time']).dt.total_seconds() / 60.0
    
    # Filtrar marcas repetidas a menos de 2 minutos del mismo empleado
    mask_duplicado = (df['Carnet_Identidad'] == df['Prev_Carnet']) & (df['Diff_Min'] < 2.0)
    df = df[~mask_duplicado].copy()

    # 2. Algoritmo de Emparejamiento por Ventana Flotante (Soporte Trasnoche)
    registros_procesados = []

    # Parámetros globales por defecto si no existen
    hora_corte_nocturno = time(17, 0) # Entradas a partir de las 17:00 son candidatas a turno nocturno
    max_duracion_turno = 16.0         # Horas máximas de un turno válido (ej. 21:00 a 06:00 = 9h)

    for carnet, group in df.groupby('Carnet_Identidad'):
        punches = group.to_dict('records')
        n = len(punches)
        i = 0

        # Obtener tipo personal y nombre si existen
        nombre_emp = punches[0].get('Nombre', 'Desconocido')
        tipo_pers = punches[0].get('Tipo Personal', 'Fijo')
        
        if df_emp is not None and not df_emp.empty:
            match_emp = df_emp[df_emp['Carnet_Identidad'].astype(str) == str(carnet)]
            if not match_emp.empty:
                nombre_emp = match_emp.iloc[0].get('Nombre', nombre_emp)
                tipo_pers = match_emp.iloc[0].get('Tipo Personal', tipo_pers)

        while i < n:
            curr = punches[i]
            curr_dt = curr['FechaHora']
            
            # Si hay un siguiente punch
            if i + 1 < n:
                next_punch = punches[i + 1]
                next_dt = next_punch['FechaHora']
                diff_hours = (next_dt - curr_dt).total_seconds() / 3600.0

                # Caso A: Emparejamiento Válido (Entrada -> Salida)
                # Ocurre si la diferencia está entre 0.25h (15 min) y 16h
                if 0.25 <= diff_hours <= max_duracion_turno:
                    fecha_jornada = curr_dt.date() # La jornada pertenece al día de Entrada
                    
                    registros_procesados.append({
                        'Carnet_Identidad': carnet,
                        'Nombre': nombre_emp,
                        'Tipo Personal': tipo_pers,
                        'Fecha': fecha_jornada,
                        'Día': _traducir_dia(fecha_jornada.strftime('%A')),
                        'Entrada': curr_dt.strftime('%H:%M'),
                        'Salida': next_dt.strftime('%H:%M'),
                        'Entrada_DT': curr_dt,
                        'Salida_DT': next_dt,
                        'Horas Trabajadas': round(diff_hours, 2),
                        'Es_Trasnoche': curr_dt.date() != next_dt.date(),
                        'Estado': 'Asistió'
                    })
                    i += 2 # Consumimos Entrada y Salida
                    continue

            # Caso B: Marcación Huérfana (Sin Salida o Entrada Solitaria)
            # Determinar si parece una Entrada o una Salida aislada según la hora
            fecha_jornada = curr_dt.date()
            if curr_dt.time() < time(12, 0) and i > 0:
                # Es una marca mañanera aislada (posible salida no emparejada)
                registros_procesados.append({
                    'Carnet_Identidad': carnet,
                    'Nombre': nombre_emp,
                    'Tipo Personal': tipo_pers,
                    'Fecha': fecha_jornada,
                    'Día': _traducir_dia(fecha_jornada.strftime('%A')),
                    'Entrada': 'Falta Marcación',
                    'Salida': curr_dt.strftime('%H:%M'),
                    'Entrada_DT': None,
                    'Salida_DT': curr_dt,
                    'Horas Trabajadas': 0.0,
                    'Es_Trasnoche': False,
                    'Estado': 'Incompleto'
                })
            else:
                # Es una marca de entrada sin salida
                registros_procesados.append({
                    'Carnet_Identidad': carnet,
                    'Nombre': nombre_emp,
                    'Tipo Personal': tipo_pers,
                    'Fecha': fecha_jornada,
                    'Día': _traducir_dia(fecha_jornada.strftime('%A')),
                    'Entrada': curr_dt.strftime('%H:%M'),
                    'Salida': 'Falta Marcación',
                    'Entrada_DT': curr_dt,
                    'Salida_DT': None,
                    'Horas Trabajadas': 0.0,
                    'Es_Trasnoche': False,
                    'Estado': 'Incompleto'
                })
            i += 1

    df_res = pd.DataFrame(registros_procesados)

    if df_res.empty:
        return _empty_attendance_df()

    # 3. Cálculo de Atrasos, Horas Extras, Banderas y Novedades
    df_res['Atraso (Minutos)'] = 0
    df_res['Horas Extras'] = 0.0
    df_res['Turnos Computados'] = df_res['Horas Trabajadas'].apply(lambda x: 1.0 if x >= 4.0 else (0.5 if x > 0 else 0.0))
    df_res['Entrada Anticipada Flag'] = False
    df_res['Salida Tardia Flag'] = False
    df_res['HE Solicitadas'] = False

    # Evaluación contra parámetros y tolerancia (si están disponibles)
    tolerancia_min = 10
    if df_params is not None and not df_params.empty:
        if 'Tolerancia_Minutos' in df_params.columns:
            tolerancia_min = df_params['Tolerancia_Minutos'].iloc[0]

    for idx, row in df_res.iterrows():
        if row['Estado'] == 'Asistió':
            # Ejemplo simplificado de regla de cálculo de atraso
            # Para turnos nocturnos (21:00 nominal):
            ent_dt = row['Entrada_DT']
            if ent_dt:
                hora_ent = ent_dt.time()
                # Si entra de noche (~21:00) o de mañana (~06:00/07:00)
                if hora_ent >= time(20, 0):
                    hora_programada = time(21, 0)
                    atraso = (ent_dt - datetime.combine(ent_dt.date(), hora_programada)).total_seconds() / 60.0
                    if atraso > tolerancia_min:
                        df_res.at[idx, 'Atraso (Minutos)'] = int(atraso)
                elif time(5, 0) <= hora_ent <= time(9, 0):
                    hora_programada = time(7, 0)
                    atraso = (ent_dt - datetime.combine(ent_dt.date(), hora_programada)).total_seconds() / 60.0
                    if atraso > tolerancia_min:
                        df_res.at[idx, 'Atraso (Minutos)'] = int(atraso)

            # Cálculo de Horas Extras si excede las 8 horas estándar
            if row['Horas Trabajadas'] > 8.0:
                df_res.at[idx, 'Horas Extras'] = round(row['Horas Trabajadas'] - 8.0, 2)
                df_res.at[idx, 'HE Solicitadas'] = True

    # Integración con Novedades / Permisos Justificados
    if df_nov is not None and not df_nov.empty:
        df_res = _aplicar_novedades(df_res, df_nov)

    return df_res


def detect_exceptions(df_resultado):
    """
    Detecta excepciones para la pantalla de Aprobaciones de Supervisores,
    incluyendo omisiones de marcación, atrasos y horas extras.
    """
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame(columns=[
            'Carnet_Identidad', 'Nombre', 'Fecha', 'Tipo Excepción',
            'Detalle Excepción', 'Valor a Revisar', 'Decisión Supervisor'
        ])

    excepciones = []

    for _, row in df_resultado.iterrows():
        carnet = row['Carnet_Identidad']
        nombre = row['Nombre']
        fecha = row['Fecha']

        # 1. Omisión de Marcación
        if row['Entrada'] == 'Falta Marcación' or row['Salida'] == 'Falta Marcación':
            excepciones.append({
                'Carnet_Identidad': carnet,
                'Nombre': nombre,
                'Fecha': fecha,
                'Tipo Excepción': 'Falta / Omisión Marcación',
                'Detalle Excepción': f"Entrada: {row['Entrada']} | Salida: {row['Salida']}",
                'Valor a Revisar': 1,
                'Decisión Supervisor': 'Pendiente'
            })

        # 2. Atrasos Significativos
        if row.get('Atraso (Minutos)', 0) > 0:
            excepciones.append({
                'Carnet_Identidad': carnet,
                'Nombre': nombre,
                'Fecha': fecha,
                'Tipo Excepción': 'Atraso',
                'Detalle Excepción': f"Atraso registrado: {row['Atraso (Minutos)']} min",
                'Valor a Revisar': row['Atraso (Minutos)'],
                'Decisión Supervisor': 'Pendiente'
            })

        # 3. Horas Extras / Trabajo en Domingo
        if row.get('HE Solicitadas', False) or row.get('Horas Extras', 0) > 0:
            excepciones.append({
                'Carnet_Identidad': carnet,
                'Nombre': nombre,
                'Fecha': fecha,
                'Tipo Excepción': 'Horas Extras / Domingo',
                'Detalle Excepción': f"Trabajo Extra: {row.get('Horas Extras', 0)} hrs",
                'Valor a Revisar': row.get('Horas Extras', 0),
                'Decisión Supervisor': 'Pendiente'
            })

    return pd.DataFrame(excepciones)


def get_canje_summary(df_resultado):
    """
    Genera el resumen de horas extras acumuladas vs faltas para canjes de bolsa de horas.
    """
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame(columns=['Carnet_Identidad', 'Nombre', 'Bolsa_HE', 'Faltas_Acumuladas', 'Saldo_Canjeable'])

    resumen = df_resultado.groupby(['Carnet_Identidad', 'Nombre']).agg(
        Bolsa_HE=('Horas Extras', 'sum'),
        Faltas_Acumuladas=('Estado', lambda x: (x == 'Incompleto').sum())
    ).reset_index()

    resumen['Saldo_Canjeable'] = resumen['Bolsa_HE'] - (resumen['Faltas_Acumuladas'] * 8.0)
    return resumen


def _traducir_dia(dia_en):
    dias = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    return dias.get(dia_en, dia_en)


def _aplicar_novedades(df_res, df_nov):
    """
    Cruza los registros con la tabla de Novedades y Permisos.
    """
    for idx, row in df_res.iterrows():
        match = df_nov[
            (df_nov['Carnet_Identidad'].astype(str) == str(row['Carnet_Identidad'])) &
            (pd.to_datetime(df_nov['Fecha']).dt.date == row['Fecha'])
        ]
        if not match.empty:
            tipo_nov = match.iloc[0].get('Tipo Novedad', 'Permiso Justificado')
            if row['Estado'] == 'Incompleto':
                df_res.at[idx, 'Estado'] = f"Justificado ({tipo_nov})"
    return df_res


def _empty_attendance_df():
    return pd.DataFrame(columns=[
        'Carnet_Identidad', 'Nombre', 'Tipo Personal', 'Fecha', 'Día',
        'Entrada', 'Salida', 'Horas Trabajadas', 'Atraso (Minutos)',
        'Horas Extras', 'Turnos Computados', 'Estado',
        'Entrada Anticipada Flag', 'Salida Tardia Flag', 'HE Solicitadas'
    ])
