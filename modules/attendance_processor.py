import pandas as pd

def process_attendance(df_bio, df_params):
    """
    Agrupa marcaciones de entrada y salida por empleado/fecha 
    y calcula horas trabajadas y minutos de atraso.
    """
    if df_bio.empty:
        return pd.DataFrame()
    
    df = df_bio.copy()
    
    # Convertir a datetime
    df['Fecha_Hora'] = pd.to_datetime(df['Fecha_Hora'], format='%d/%m/%Y %H:%M', errors='coerce')
    df = df.dropna(subset=['Fecha_Hora'])
    
    df['Fecha'] = df['Fecha_Hora'].dt.date
    
    records = []
    
    # Agrupar por ID, Nombre y Fecha
    for (emp_id, nombre, fecha), group in df.groupby(['ID', 'Nombre', 'Fecha']):
        entradas = group[group['Estado'].str.strip().str.capitalize() == 'Entrada']
        salidas = group[group['Estado'].str.strip().str.capitalize() == 'Salida']
        
        hora_entrada = entradas['Fecha_Hora'].min() if not entradas.empty else None
        hora_salida = salidas['Fecha_Hora'].max() if not salidas.empty else None
        
        horas_trabajadas = 0.0
        atraso_min = 0
        
        if pd.notnull(hora_entrada) and pd.notnull(hora_salida):
            duracion = (hora_salida - hora_entrada).total_seconds() / 3600.0
            horas_trabajadas = round(duracion, 2)
            
            # Evaluación de atraso tomando la hora programada de ingreso habitual (08:00) + 10 min tolerancia
            hora_esperada = hora_entrada.replace(hour=8, minute=0, second=0)
            hora_limite = hora_entrada.replace(hour=8, minute=10, second=0)
            
            if hora_entrada > hora_limite:
                atraso_min = int((hora_entrada - hora_esperada).total_seconds() / 60)
        
        records.append({
            'ID': emp_id,
            'Nombre': nombre,
            'Fecha': fecha.strftime('%d/%m/%Y'),
            'Entrada': hora_entrada.strftime('%H:%M') if pd.notnull(hora_entrada) else 'Falta Marcación',
            'Salida': hora_salida.strftime('%H:%M') if pd.notnull(hora_salida) else 'Falta Marcación',
            'Horas Trabajadas': horas_trabajadas,
            'Atraso (Minutos)': atraso_min
        })
        
    return pd.DataFrame(records)
