import pandas as pd
import numpy as np
from datetime import datetime, time

TOLERANCIA_MINUTOS = 10
DESCUENTO_COMIDA_HORAS = 0.5  # 30 minutos obligatorios

def process_attendance(df_bio, df_params=None, df_nov=None, df_emp=None):
    if df_bio is None or df_bio.empty:
        return pd.DataFrame()

    df = df_bio.copy()

    # 1. Identificación flexible de columnas
    cols = {str(c).strip().lower(): c for c in df.columns}
    
    col_id = next((cols[k] for k in cols if any(x in k for x in ['id', 'carnet', 'ci', 'codigo'])), df.columns[0])
    col_nombre = next((cols[k] for k in cols if any(x in k for x in ['nombre', 'empleado', 'trabajador'])), df.columns[1] if len(df.columns) > 1 else col_id)
    col_fecha = next((cols[k] for k in cols if any(x in k for x in ['fecha', 'hora', 'marcacion', 'tiempo'])), df.columns[2] if len(df.columns) > 2 else col_id)
    col_tipo = next((cols[k] for k in cols if any(x in k for x in ['tipo', 'movimiento', 'evento', 'estado'])), None)

    # 2. Parseo de fechas y ordenamiento
    df['dt_parsed'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['dt_parsed']).sort_values([col_id, 'dt_parsed'])

    # 3. Diccionario de modalidad de contratación desde Maestro
    dict_tipo_personal = {}
    if df_emp is not None and not df_emp.empty:
        emp_cols = {str(c).strip().lower(): c for c in df_emp.columns}
        c_emp_id = next((emp_cols[k] for k in emp_cols if any(x in k for x in ['id', 'carnet', 'ci', 'codigo'])), None)
        c_emp_tipo = next((emp_cols[k] for k in emp_cols if any(x in k for x in ['tipo', 'modalidad', 'contrato'])), None)
        if c_emp_id and c_emp_tipo:
            dict_tipo_personal = dict(zip(df_emp[c_emp_id].astype(str).str.strip(), df_emp[c_emp_tipo].astype(str).str.strip()))

    registros = []

    # 4. Procesamiento por Empleado
    for (emp_id, emp_nombre), group in df.groupby([col_id, col_nombre]):
        emp_id_str = str(emp_id).strip()
        tipo_personal = dict_tipo_personal.get(emp_id_str, "Fijo").capitalize()
        punches = group.to_dict('records')

        i = 0
        while i < len(punches):
            p_in = punches[i]
            dt_in = p_in['dt_parsed']
            p_type = str(p_in.get(col_tipo, '')).strip().lower() if col_tipo else ''

            if 'salida' not in p_type:
                dt_out = None
                j = i + 1
                while j < len(punches):
                    next_dt = punches[j]['dt_parsed']
                    next_type = str(punches[j].get(col_tipo, '')).strip().lower() if col_tipo else ''
                    
                    if (next_dt - dt_in).total_seconds() <= 16 * 3600:
                        if 'salida' in next_type or j == len(punches) - 1 or (punches[j+1]['dt_parsed'] - next_dt).total_seconds() > 4 * 3600:
                            dt_out = next_dt
                            i = j
                            break
                    j += 1

                fecha_str = dt_in.strftime('%Y-%m-%d')
                hora_in_str = dt_in.strftime('%H:%M')
                hora_out_str = dt_out.strftime('%H:%M') if dt_out else 'Falta Marcación'
                
                dia_semana = dt_in.weekday()
                es_domingo = (dia_semana == 6)
                es_viernes = (dia_semana == 4)
                
                es_nocturno = (dt_in.hour >= 18 or dt_in.hour < 5)
                turno_label = 'Nocturno' if es_nocturno else 'Diurno'

                if dt_out:
                    horas_brutas = (dt_out - dt_in).total_seconds() / 3600.0
                    if dt_out <= dt_in:
                        horas_brutas += 24.0
                else:
                    horas_brutas = 0.0

                horas_netas = max(0.0, round(horas_brutas - DESCUENTO_COMIDA_HORAS, 2)) if horas_brutas > 0 else 0.0

                hora_esperada = time(22, 0) if es_nocturno else time(7, 30)
                dt_esperada = datetime.combine(dt_in.date(), hora_esperada)
                
                minutos_diferencia = (dt_in - dt_esperada).total_seconds() / 60.0
                atraso_minutos = max(0, int(minutos_diferencia - TOLERANCIA_MINUTOS)) if minutos_diferencia > TOLERANCIA_MINUTOS else 0

                # Verificación de permisos registrados en novedades
                tiene_permiso = False
                if df_nov is not None and not df_nov.empty:
                    try:
                        nov_cols = {str(c).strip().lower(): c for c in df_nov.columns}
                        c_nov_id = next((nov_cols[k] for k in nov_cols if any(x in k for x in ['id', 'carnet', 'ci', 'codigo'])), None)
                        c_nov_f = next((nov_cols[k] for k in nov_cols if 'fecha' in k), None)
                        if c_nov_id and c_nov_f:
                            match_permiso = df_nov[
                                (df_nov[c_nov_id].astype(str).str.strip() == emp_id_str) &
                                (df_nov[c_nov_f].astype(str).str.contains(fecha_str))
                            ]
                            if not match_permiso.empty:
                                tiene_permiso = True
                                atraso_minutos = 0
                    except Exception:
                        pass

                turnos_computados = 1.0
                horas_extras = 0.0
                horas_nocturnas = horas_netas if es_nocturno else 0.0

                if "Jornal" in tipo_personal:
                    turnos_computados = 1.5 if (es_nocturno and (es_domingo or es_viernes)) or horas_netas >= 11.5 else 1.0
                    horas_extras = 0.0
                elif es_nocturno:
                    if es_domingo or es_viernes:
                        turnos_computados = 1.5
                        horas_extras = 0.0
                    else:
                        turnos_computados = 1.0
                        if horas_netas > 7.0:
                            horas_extras = round(horas_netas - 7.0, 2)
                else:
                    turnos_computados = 1.0
                    if horas_netas > 8.0:
                        horas_extras = round(horas_netas - 8.0, 2)

                # Clasificación de Faltas
                es_falta = (not dt_out)
                falta_justificada = 1 if (es_falta and tiene_permiso) else 0
                falta_injustificada = 1 if (es_falta and not tiene_permiso) else 0

                desfase_ingreso = False
                if horas_netas >= 7.0 and minutos_diferencia > 45:
                    desfase_ingreso = True

                registros.append({
                    'ID': emp_id_str,
                    'Nombre': str(emp_nombre),
                    'Tipo Personal': tipo_personal,
                    'Fecha': fecha_str,
                    'Día': dt_in.strftime('%A'),
                    'Entrada': hora_in_str,
                    'Salida': hora_out_str,
                    'Horas Trabajadas': horas_netas,
                    'Atraso (Minutos)': atraso_minutos,
                    'Falta Justificada': falta_justificada,
                    'Falta Injustificada': falta_injustificada,
                    'Horas Extras': horas_extras,
                    'Horas Nocturnas': horas_nocturnas,
                    'Turnos Computados': turnos_computados,
                    'Turno Dominante': turno_label,
                    'Desfase Ingreso': desfase_ingreso,
                    'Estado': 'OK' if dt_out else 'Revisar Marcación'
                })
            i += 1

    return pd.DataFrame(registros)


def detect_exceptions(df_resultado):
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    excepciones = []

    df_temp = df_resultado.copy()
    df_temp['dt_fecha'] = pd.to_datetime(df_temp['Fecha'])
    df_temp['Semana'] = df_temp['dt_fecha'].dt.isocalendar().week

    dias_por_semana = df_temp.groupby(['ID', 'Semana'])['Fecha'].nunique().reset_index()
    semanas_7dias = set(
        dias_por_semana[dias_por_semana['Fecha'] >= 7].set_index(['ID', 'Semana']).index
    )

    for _, row in df_resultado.iterrows():
        emp_id = row['ID']
        emp_nom = row['Nombre']
        fecha = row['Fecha']
        dt_f = pd.to_datetime(fecha)
        semana = dt_f.isocalendar().week

        # Caso 1: Marcación omisa / Falta
        if row['Estado'] != 'OK' or row['Salida'] == 'Falta Marcación':
            tipo_inicial = 'Justificada' if row.get('Falta Justificada', 0) == 1 else 'Injustificada'
            excepciones.append({
                'ID': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': 'Falta / Omisión Marcación',
                'Detalle Excepción': f"Entrada: {row['Entrada']} | Salida: {row['Salida']}",
                'Valor a Revisar': '1 Falta a Procesar',
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': tipo_inicial,
                'Observaciones': ''
            })

        # Caso 2: Horas Extras acumuladas (Opción de pago o acumular próx. mes)
        if row['Horas Extras'] > 0:
            excepciones.append({
                'ID': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': 'Horas Extras',
                'Detalle Excepción': f"Marcación excedente: {row['Horas Extras']} hrs",
                'Valor a Revisar': f"{row['Horas Extras']} hrs HE",
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': ''
            })

        # Caso 3: 7º día trabajado en la semana
        if (emp_id, semana) in semanas_7dias:
            excepciones.append({
                'ID': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': '7º Día Laborado',
                'Detalle Excepción': f"Empleado registró asistencia los 7 días de la semana {semana}",
                'Valor a Revisar': '1 Día Excedente',
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': ''
            })

        # Caso 4: Desfase de Horario de Ingreso
        if row.get('Desfase Ingreso', False):
            excepciones.append({
                'ID': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': 'Desfase Horario Ingreso',
                'Detalle Excepción': f"Ingresó a las {row['Entrada']} completando {row['Horas Trabajadas']} hrs",
                'Valor a Revisar': f"Entrada {row['Entrada']}",
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': ''
            })

    return pd.DataFrame(excepciones)


def get_canje_summary(df_resultado):
    """
    Genera un resumen masivo por empleado para el Canje de Bolsa de Horas Extras por Faltas.
    Calcula exactamente cuántos días completos (enteros) se pueden canjear según la jornada:
    - Diurno: 8 hrs = 1 día
    - Nocturno: 7 hrs = 1 día
    """
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    resumen = []
    for (emp_id, emp_nom), grp in df_resultado.groupby(['ID', 'Nombre']):
        total_he = grp['Horas Extras'].sum()
        total_faltas = (grp['Falta Justificada'] + grp['Falta Injustificada']).sum()
        
        # Determinar turno dominante
        turno_dom = grp['Turno Dominante'].mode()[0] if not grp['Turno Dominante'].empty else 'Diurno'
        costo_hora_dia = 7.0 if turno_dom == 'Nocturno' else 8.0

        # Cálculo de días máximos canjeables (Entero estricto, sin decimales)
        dias_canjeables_max = int(total_he // costo_hora_dia)

        if total_he > 0 or total_faltas > 0:
            resumen.append({
                'ID': emp_id,
                'Nombre': emp_nom,
                'Turno Dominante': turno_dom,
                'Horas Costo por Día': costo_hora_dia,
                'Bolsa HE Acumulada (hrs)': round(total_he, 2),
                'Días Máx. Canjeables': dias_canjeables_max,
                'Faltas Registradas': int(total_faltas),
                'Días a Canjear (Aplicar)': 0,
                'Estado Canje': 'Sin Aplicar'
            })

    return pd.DataFrame(resumen)
