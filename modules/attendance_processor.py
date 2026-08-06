import pandas as pd
import numpy as np
from datetime import datetime, time

def process_attendance(df_biometrico, df_empleados, df_novedades=None, df_canjes=None):
    """
    Procesa las marcaciones del biométrico completando el calendario continuo por empleado
    para detectar ausencias (faltas injustificadas) en días sin marcación.
    """
    if df_biometrico.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Copia de trabajo
    df_bio = df_biometrico.copy()

    # Normalizar columnas de fecha y hora
    df_bio['Fecha_DT'] = pd.to_datetime(df_bio['Fecha'], errors='coerce')
    df_bio = df_bio.dropna(subset=['Fecha_DT'])

    if df_bio.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Asegurar mapeo con Maestro de Empleados
    df_bio['ID_Emp'] = df_bio['ID'].astype(str).str.strip()
    
    emp_map = {}
    if not df_empleados.empty and 'ID' in df_empleados.columns:
        df_emp_temp = df_empleados.copy()
        df_emp_temp['ID_Str'] = df_emp_temp['ID'].astype(str).str.strip()
        emp_map = df_emp_temp.set_index('ID_Str')['Nombre'].to_dict()

    # Rango global de fechas del período analizado
    min_date = df_bio['Fecha_DT'].min()
    max_date = df_bio['Fecha_DT'].max()
    all_dates = pd.date_range(start=min_date, end=max_date, freq='D')

    # Obtener lista de todos los empleados presentes en biométrico o maestro
    unique_emp_ids = df_bio['ID_Emp'].unique()

    # Mapeo de Novedades
    novedades_dict = {}
    if df_novedades is not None and not df_novedades.empty:
        for _, row in df_novedades.iterrows():
            emp_id = str(row.get('ID_Empleado', '')).strip()
            f_inicio = pd.to_datetime(row.get('Fecha_Inicio'), errors='coerce')
            f_fin = pd.to_datetime(row.get('Fecha_Fin'), errors='coerce')
            tipo_nov = row.get('Tipo_Novedad', 'Permiso')
            
            if pd.notnull(f_inicio) and pd.notnull(f_fin) and emp_id:
                cur_d = f_inicio
                while cur_d <= f_fin:
                    key = (emp_id, cur_d.strftime('%Y-%m-%d'))
                    novedades_dict[key] = tipo_nov
                    cur_d += pd.Timedelta(days=1)

    # Mapeo de Canjes
    canjes_set = set()
    if df_canjes is not None and not df_canjes.empty:
        for _, row in df_canjes.iterrows():
            emp_id = str(row.get('ID_Empleado', '')).strip()
            f_canje = pd.to_datetime(row.get('Fecha'), errors='coerce')
            if pd.notnull(f_canje) and emp_id:
                canjes_set.add((emp_id, f_canje.strftime('%Y-%m-%d')))

    processed_rows = []
    excepciones_list = []

    for emp_id in unique_emp_ids:
        emp_nombre = emp_map.get(emp_id, df_bio[df_bio['ID_Emp'] == emp_id]['Nombre'].iloc[0] if len(df_bio[df_bio['ID_Emp'] == emp_id]) > 0 else 'Desconocido')
        tipo_personal = 'Fijo'

        # Filtrar marcaciones del empleado
        df_emp_bio = df_bio[df_bio['ID_Emp'] == emp_id]

        for current_date in all_dates:
            date_str = current_date.strftime('%Y-%m-%d')
            day_name = current_date.strftime('%A')
            is_sunday = (current_date.weekday() == 6)

            # Buscar marcaciones en este día
            day_records = df_emp_bio[df_emp_bio['Fecha_DT'] == current_date]

            # Verificar si existe Novedad / Permiso
            nov_key = (emp_id, date_str)
            tiene_novedad = nov_key in novedades_dict
            tipo_novedad = novedades_dict.get(nov_key, None)

            # CASO 1: No hay marcación en el biométrico
            if day_records.empty:
                if is_sunday:
                    # Domingo sin marcación = Descanso Semanal
                    processed_rows.append({
                        'ID': emp_id,
                        'Nombre': emp_nombre,
                        'Tipo Personal': tipo_personal,
                        'Fecha': date_str,
                        'Día': day_name,
                        'Entrada': '-',
                        'Salida': '-',
                        'Horas Trabajadas': 0.0,
                        'Atraso (Minutos)': 0,
                        'Falta Justificada': 0,
                        'Falta Injustificada': 0,
                        'Horas Extras 50%': 0.0,
                        'Horas Extras 100%': 0.0,
                        'Turnos Completados': 0.0,
                        'Estado': 'DESCANSO'
                    })
                elif tiene_novedad:
                    # Día laboral sin marcación, pero JUSTIFICADO por Permiso/Novedad
                    processed_rows.append({
                        'ID': emp_id,
                        'Nombre': emp_nombre,
                        'Tipo Personal': tipo_personal,
                        'Fecha': date_str,
                        'Día': day_name,
                        'Entrada': '-',
                        'Salida': '-',
                        'Horas Trabajadas': 0.0,
                        'Atraso (Minutos)': 0,
                        'Falta Justificada': 1,
                        'Falta Injustificada': 0,
                        'Horas Extras 50%': 0.0,
                        'Horas Extras 100%': 0.0,
                        'Turnos Completados': 0.0,
                        'Estado': f'LICENCIA ({tipo_novedad})'
                    })
                else:
                    # Día laboral sin marcación y SIN permiso = FALTA INJUSTIFICADA
                    processed_rows.append({
                        'ID': emp_id,
                        'Nombre': emp_nombre,
                        'Tipo Personal': tipo_personal,
                        'Fecha': date_str,
                        'Día': day_name,
                        'Entrada': '-',
                        'Salida': '-',
                        'Horas Trabajadas': 0.0,
                        'Atraso (Minutos)': 0,
                        'Falta Justificada': 0,
                        'Falta Injustificada': 1,
                        'Horas Extras 50%': 0.0,
                        'Horas Extras 100%': 0.0,
                        'Turnos Completados': 0.0,
                        'Estado': 'FALTA INJUSTIFICADA'
                    })

                    # Generar Excepción de Falta Injustificada
                    excepciones_list.append({
                        'ID': emp_id,
                        'Nombre': emp_nombre,
                        'Fecha': date_str,
                        'Tipo Excepción': 'Falta Injustificada',
                        'Detalle': 'Sin marcación de entrada ni salida en día laboral',
                        'Estado': 'PENDIENTE'
                    })

            # CASO 2: Sí existen marcaciones en el día
            else:
                # Obtener primera entrada y última salida
                entradas = day_records['Hora'].tolist() if 'Hora' in day_records.columns else []
                
                # Asumiendo estructura de hora o registros de entrada/salida
                if 'Entrada' in day_records.columns and 'Salida' in day_records.columns:
                    h_entrada = day_records['Entrada'].iloc[0]
                    h_salida = day_records['Salida'].iloc[0]
                else:
                    h_entrada = day_records['Hora'].min() if len(day_records) > 0 else '-'
                    h_salida = day_records['Hora'].max() if len(day_records) > 1 else '-'

                # Evaluación de marcación incompleta
                if h_entrada == '-' or h_salida == '-' or h_entrada == h_salida:
                    if tiene_novedad:
                        fj, fij = 1, 0
                        estado_row = f'LICENCIA ({tipo_novedad})'
                    else:
                        fj, fij = 0, 1
                        estado_row = 'MARCACIÓN INCOMPLETA'
                        excepciones_list.append({
                            'ID': emp_id,
                            'Nombre': emp_nombre,
                            'Fecha': date_str,
                            'Tipo Excepción': 'Falta Marcación',
                            'Detalle': 'Registro incompleto de Entrada o Salida',
                            'Estado': 'PENDIENTE'
                        })

                    processed_rows.append({
                        'ID': emp_id,
                        'Nombre': emp_nombre,
                        'Tipo Personal': tipo_personal,
                        'Fecha': date_str,
                        'Día': day_name,
                        'Entrada': str(h_entrada),
                        'Salida': str(h_salida),
                        'Horas Trabajadas': 0.0,
                        'Atraso (Minutos)': 0,
                        'Falta Justificada': fj,
                        'Falta Injustificada': fij,
                        'Horas Extras 50%': 0.0,
                        'Horas Extras 100%': 0.0,
                        'Turnos Completados': 0.0,
                        'Estado': estado_row
                    })
                else:
                    # Marcación completa: cálculo de horas trabajadas y retrasos
                    try:
                        t_in = pd.to_datetime(f"{date_str} {h_entrada}")
                        t_out = pd.to_datetime(f"{date_str} {h_salida}")
                        if t_out < t_in:
                            t_out += pd.Timedelta(days=1)
                        
                        duracion_hrs = round((t_out - t_in).total_seconds() / 3600.0, 2)
                    except:
                        duracion_hrs = 8.0

                    # Umbral de jornada estándar (8 horas)
                    jornada_std = 8.0
                    
                    # Cálculo simplificado de atraso si la entrada supera las 07:15
                    atraso_min = 0
                    try:
                        h_in_obj = datetime.strptime(str(h_entrada)[:5], "%H:%M").time()
                        h_ref = time(7, 15)
                        if h_in_obj > h_ref:
                            atraso_min = int((datetime.combine(datetime.today(), h_in_obj) - datetime.combine(datetime.today(), h_ref)).total_seconds() / 60)
                    except:
                        atraso_min = 0

                    if atraso_min > 0:
                        excepciones_list.append({
                            'ID': emp_id,
                            'Nombre': emp_nombre,
                            'Fecha': date_str,
                            'Tipo Excepción': 'Atraso',
                            'Detalle': f'Atraso registrado de {atraso_min} minutos',
                            'Estado': 'PENDIENTE'
                        })

                    # Calculo de Horas Extras
                    he_50 = max(0.0, round(duracion_hrs - jornada_std, 2)) if not is_sunday else 0.0
                    he_100 = duracion_hrs if is_sunday else 0.0

                    if (emp_id, date_str) in canjes_set:
                        he_50 = 0.0
                        he_100 = 0.0

                    turnos_comp = 1.0 if duracion_hrs >= 4.0 else 0.5

                    processed_rows.append({
                        'ID': emp_id,
                        'Nombre': emp_nombre,
                        'Tipo Personal': tipo_personal,
                        'Fecha': date_str,
                        'Día': day_name,
                        'Entrada': str(h_entrada),
                        'Salida': str(h_salida),
                        'Horas Trabajadas': duracion_hrs,
                        'Atraso (Minutos)': atraso_min,
                        'Falta Justificada': 0,
                        'Falta Injustificada': 0,
                        'Horas Extras 50%': he_50,
                        'Horas Extras 100%': he_100,
                        'Turnos Completados': turnos_comp,
                        'Estado': 'NORMAL'
                    })

    df_procesado = pd.DataFrame(processed_rows)
    df_excepciones = pd.DataFrame(excepciones_list)
    
    # Resumen consolidado por empleado
    if not df_procesado.empty:
        df_resumen = df_procesado.groupby(['ID', 'Nombre']).agg({
            'Horas Trabajadas': 'sum',
            'Atraso (Minutos)': 'sum',
            'Horas Extras 50%': 'sum',
            'Horas Extras 100%': 'sum',
            'Falta Justificada': 'sum',
            'Falta Injustificada': 'sum',
            'Turnos Completados': 'sum'
        }).reset_index()
    else:
        df_resumen = pd.DataFrame()

    return df_procesado, df_excepciones, df_resumen
