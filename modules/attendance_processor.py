import pandas as pd
from datetime import datetime, time

def calcular_horas_nocturnas(entrada, salida):
    """Calcula la cantidad de horas trabajadas dentro del rango nocturno (20:00 a 06:00)."""
    if pd.isnull(entrada) or pd.isnull(salida):
        return 0.0
    
    inicio_noche = datetime.combine(entrada.date(), time(20, 0))
    fin_noche = datetime.combine(entrada.date() + pd.Timedelta(days=1), time(6, 0))
    inicio_noche_prev = datetime.combine(entrada.date() - pd.Timedelta(days=1), time(20, 0))
    fin_noche_prev = datetime.combine(entrada.date(), time(6, 0))
    
    horas_nocturnas = 0.0
    
    # Tramo 00:00 - 06:00
    overlap_inicio = max(entrada, inicio_noche_prev)
    overlap_fin = min(salida, fin_noche_prev)
    if overlap_fin > overlap_inicio:
        horas_nocturnas += (overlap_fin - overlap_inicio).total_seconds() / 3600.0
        
    # Tramo 20:00 - 06:00 siguiente
    overlap_inicio = max(entrada, inicio_noche)
    overlap_fin = min(salida, fin_noche)
    if overlap_fin > overlap_inicio:
        horas_nocturnas += (overlap_fin - overlap_inicio).total_seconds() / 3600.0

    return round(horas_nocturnas, 2)

def process_attendance(df_bio, df_params, df_novedades=None, df_empleados=None):
    """
    Procesa marcaciones de asistencia puras:
    - Reporta Días, Horas Trabajadas, Atrasos (min), Horas Extras y Horas Nocturnas.
    - Identifica tipo de turno (Diurno / Nocturno) y cómputo de turno para Jornaleros.
    """
    if df_bio.empty:
        return pd.DataFrame()
    
    df = df_bio.copy()
    
    df['Fecha_Hora'] = pd.to_datetime(df['Fecha_Hora'], format='%d/%m/%Y %H:%M', errors='coerce')
    df = df.dropna(subset=['Fecha_Hora'])
    df['Fecha'] = df['Fecha_Hora'].dt.date
    
    tolerancia_min = 10
    jornada_diurna = 8.5
    
    if df_params is not None and not df_params.empty:
        try:
            tol_row = df_params[df_params['Parametro'].str.strip() == 'Tolerancia_Retraso_Min']
            if not tol_row.empty:
                tolerancia_min = int(tol_row['Valor'].values[0])
            jornada_row = df_params[df_params['Parametro'].str.strip() == 'Horas_Jornada_Diurna']
            if not jornada_row.empty:
                jornada_diurna = float(str(jornada_row['Valor'].values[0]).replace(',', '.'))
        except Exception:
            pass

    records = []
    
    for (emp_id, nombre, fecha), group in df.groupby(['ID', 'Nombre', 'Fecha']):
        entradas = group[group['Estado'].str.strip().str.capitalize() == 'Entrada']
        salidas = group[group['Estado'].str.strip().str.capitalize() == 'Salida']
        
        hora_entrada = entradas['Fecha_Hora'].min() if not entradas.empty else None
        hora_salida = salidas['Fecha_Hora'].max() if not salidas.empty else None
        
        horas_trabajadas = 0.0
        atraso_min = 0
        horas_extras = 0.0
        horas_nocturnas = 0.0
        es_domingo = fecha.weekday() == 6
        
        if pd.notnull(hora_entrada) and pd.notnull(hora_salida):
            duracion = (hora_salida - hora_entrada).total_seconds() / 3600.0
            horas_trabajadas = round(duracion, 2)
            
            # Evaluación de Atraso
            hora_esperada = hora_entrada.replace(hour=8, minute=0, second=0)
            hora_limite = hora_entrada.replace(hour=8, minute=tolerancia_min, second=0)
            
            if hora_entrada > hora_limite:
                atraso_min = int((hora_entrada - hora_esperada).total_seconds() / 60)
                
            # Descuento de atraso si existe novedad/permiso justificado
            if df_novedades is not None and not df_novedades.empty:
                permiso = df_novedades[
                    (df_novedades['ID'].astype(str) == str(emp_id)) & 
                    (df_novedades['Fecha'].astype(str) == fecha.strftime('%d/%m/%Y'))
                ]
                if not permiso.empty:
                    atraso_min = 0
            
            # Excedente de horas
            if horas_trabajadas > jornada_diurna:
                horas_extras = round(horas_trabajadas - jornada_diurna, 2)
                
            # Cómputo horas nocturnas
            horas_nocturnas = calcular_horas_nocturnas(hora_entrada, hora_salida)

        # Determinar tipo de turno dominante (Diurno vs Nocturno)
        tipo_turno = "Nocturno" if horas_nocturnas > (horas_trabajadas / 2) and horas_trabajadas > 0 else "Diurno"

        # Cómputo de Jornada / Turnos para Jornaleros (1 Turno vs 1.5 Turnos)
        if horas_trabajadas >= 12:
            computo_jornal = "1.5 Turnos"
        elif horas_trabajadas > 0:
            computo_jornal = "1 Turno"
        else:
            computo_jornal = "0 Turnos"

        records.append({
            'ID': emp_id,
            'Nombre': nombre,
            'Fecha': fecha.strftime('%d/%m/%Y'),
            'Tipo Día': 'Domingo' if es_domingo else 'Hábil',
            'Entrada': hora_entrada.strftime('%H:%M') if pd.notnull(hora_entrada) else 'Falta Marcación',
            'Salida': hora_salida.strftime('%H:%M') if pd.notnull(hora_salida) else 'Falta Marcación',
            'Horas Trabajadas': horas_trabajadas,
            'Atraso (Minutos)': atraso_min,
            'Horas Extras': horas_extras,
            'Horas Nocturnas': horas_nocturnas,
            'Turno Dominante': tipo_turno,
            'Computo Jornalero': computo_jornal
        })
        
    return pd.DataFrame(records)
