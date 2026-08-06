import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta

TOLERANCIA_MINUTOS = 10
DESCUENTO_COMIDA_HORAS = 0.5  # 30 minutos obligatorios

DIAS_ESPANOL = {
    0: 'Lunes',
    1: 'Martes',
    2: 'Miércoles',
    3: 'Jueves',
    4: 'Viernes',
    5: 'Sábado',
    6: 'Domingo'
}

def clean_str(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    txt = str(val).strip().upper()
    if txt.endswith('.0'):
        txt = txt[:-2]
    return txt

def process_attendance(df_bio, df_params=None, df_nov=None, df_emp=None, _nov_mgr=None):
    if df_bio is None or df_bio.empty:
        return pd.DataFrame()

    df = df_bio.copy()

    # 1. Identificación flexible de columnas en el Biométrico
    cols = {str(c).strip().lower(): c for c in df.columns}
    
    col_id = next((cols[k] for k in cols if any(x in k for x in ['id', 'carnet', 'ci', 'codigo'])), df.columns[0])
    col_nombre = next((cols[k] for k in cols if any(x in k for x in ['nombre', 'empleado', 'trabajador'])), df.columns[1] if len(df.columns) > 1 else col_id)
    col_fecha = next((cols[k] for k in cols if any(x in k for x in ['fecha', 'hora', 'marcacion', 'tiempo'])), df.columns[2] if len(df.columns) > 2 else col_id)
    col_tipo = next((cols[k] for k in cols if any(x in k for x in ['tipo', 'movimiento', 'evento', 'estado'])), None)

    # Parseo de fechas
    df['dt_parsed'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['dt_parsed']).sort_values([col_id, 'dt_parsed'])

    if df.empty:
        return pd.DataFrame()

    df['raw_id_clean'] = df[col_id].apply(clean_str)
    df['raw_nombre_clean'] = df[col_nombre].apply(clean_str) if col_nombre else df['raw_id_clean']
    df['fecha_dt'] = df['dt_parsed'].dt.date

    # 2. Mapeo inteligente con el Maestro de Empleados para unificar CI y Nombres
    dict_tipo_personal = {}
    dict_turno_personal = {}
    dict_nombres_master = {}
    
    mapping_bio_to_ci = {}

    if df_emp is not None and not df_emp.empty:
        emp_cols = {str(c).strip().lower(): c for c in df_emp.columns}
        c_emp_id = next((emp_cols[k] for k in emp_cols if any(x in k for x in ['carnet', 'ci', 'id', 'codigo'])), None)
        c_emp_nom = next((emp_cols[k] for k in emp_cols if any(x in k for x in ['nombre', 'empleado', 'trabajador'])), None)
        c_emp_tipo = next((emp_cols[k] for k in emp_cols if any(x in k for x in ['tipo', 'modalidad', 'contrato'])), None)
        c_emp_turno = next((emp_cols[k] for k in emp_cols if any(x in k for x in ['turno', 'horario'])), None)

        name_to_ci_master = {}

        for _, row in df_emp.iterrows():
            if c_emp_id:
                ci_official = clean_str(row[c_emp_id])
                if not ci_official:
                    continue
                
                nom_official = str(row[c_emp_nom]).strip() if c_emp_nom and pd.notna(row[c_emp_nom]) else ci_official
                dict_nombres_master[ci_official] = nom_official
                
                if c_emp_nom:
                    name_clean = clean_str(row[c_emp_nom])
                    if name_clean:
                        name_to_ci_master[name_clean] = ci_official

                if c_emp_tipo and pd.notna(row[c_emp_tipo]):
                    dict_tipo_personal[ci_official] = str(row[c_emp_tipo]).strip()
                if c_emp_turno and pd.notna(row[c_emp_turno]):
                    dict_turno_personal[ci_official] = str(row[c_emp_turno]).strip()

        # Vincular marcaciones biométricas a su CI oficial del Maestro
        for _, row in df[['raw_id_clean', 'raw_nombre_clean']].drop_duplicates().iterrows():
            raw_id = row['raw_id_clean']
            raw_name = row['raw_nombre_clean']

            if raw_id in dict_nombres_master:
                mapping_bio_to_ci[raw_id] = raw_id
            elif raw_name in name_to_ci_master:
                mapping_bio_to_ci[raw_id] = name_to_ci_master[raw_name]
            elif raw_id in name_to_ci_master:
                mapping_bio_to_ci[raw_id] = name_to_ci_master[raw_id]
            else:
                mapping_bio_to_ci[raw_id] = raw_id

    # Asignar CI oficial unificado
    df['emp_id_clean'] = df['raw_id_clean'].map(lambda x: mapping_bio_to_ci.get(x, x))

    # Pre-agrupar marcaciones por (CI Unificado, fecha)
    bio_by_emp_date = {}
    for row in df.to_dict('records'):
        key = (row['emp_id_clean'], row['fecha_dt'])
        if key not in bio_by_emp_date:
            bio_by_emp_date[key] = []
        bio_by_emp_date[key].append(row)

    min_date = df['dt_parsed'].min().date()
    max_date = df['dt_parsed'].max().date()
    rango_dias = pd.date_range(min_date, max_date)

    # Lista total de empleados unificada sin duplicados
    emp_ids_bio = list(set(df['emp_id_clean'].unique()))
    emp_ids_master = list(dict_nombres_master.keys())
    todos_emp_ids = sorted(list(set(emp_ids_bio + emp_ids_master)))

    # Pre-cargar Novedades
    nov_map = {}
    if _nov_mgr:
        try:
            todas_nov = _nov_mgr.obtener_todas_novedades()
            if isinstance(todas_nov, pd.DataFrame):
                todas_nov = todas_nov.to_dict('records')
            for n in todas_nov:
                e_id = clean_str(n.get('empleado_id', ''))
                f_ini_str = str(n.get('fecha_inicio', ''))
                f_fin_str = str(n.get('fecha_fin', ''))
                t_nov = n.get('tipo_novedad', '')
                just = n.get('justificacion', '')
                if e_id and f_ini_str and f_fin_str:
                    try:
                        d_start = datetime.strptime(f_ini_str[:10], '%Y-%m-%d').date()
                        d_end = datetime.strptime(f_fin_str[:10], '%Y-%m-%d').date()
                        curr = d_start
                        while curr <= d_end:
                            nov_map[(e_id, curr.strftime('%Y-%m-%d'))] = {
                                "tipo_novedad": t_nov,
                                "justificacion": just
                            }
                            curr += timedelta(days=1)
                    except Exception:
                        pass
        except Exception:
            pass

    def obtener_novedad(e_id, f_str):
        if (e_id, f_str) in nov_map:
            return nov_map[(e_id, f_str)]
        if _nov_mgr:
            try:
                return _nov_mgr.evaluar_impacto_dia(e_id, f_str)
            except Exception:
                return None
        return None

    bio_names_map = {}
    for row in df[['emp_id_clean', 'raw_nombre_clean']].drop_duplicates('emp_id_clean').to_dict('records'):
        bio_names_map[row['emp_id_clean']] = row['raw_nombre_clean']

    registros = []

    # 3. Iteración por Empleado Unificado y Día
    for emp_id_str in todos_emp_ids:
        emp_nombre = dict_nombres_master.get(emp_id_str) or bio_names_map.get(emp_id_str) or f"EMP-{emp_id_str}"
        tipo_personal = dict_tipo_personal.get(emp_id_str, "Fijo").capitalize()
        turno_asignado_base = dict_turno_personal.get(emp_id_str, "Diurno").capitalize()

        for single_date in rango_dias:
            fecha_dt = single_date.date()
            fecha_str = fecha_dt.strftime('%Y-%m-%d')
            dia_semana = fecha_dt.weekday()
            dia_nombre_esp = DIAS_ESPANOL.get(dia_semana, fecha_dt.strftime('%A'))
            
            es_domingo = (dia_semana == 6)
            es_sabado = (dia_semana == 5)
            es_viernes = (dia_semana == 4)

            nov_act = obtener_novedad(emp_id_str, fecha_str)
            turno_asignado_dia = turno_asignado_base

            if nov_act:
                t_nov_type = str(nov_act.get("tipo_novedad", "")).upper()
                just_txt = str(nov_act.get("justificacion", "")).upper()

                if t_nov_type == "CAMBIO_TURNO_NOCTURNO" or (t_nov_type == "CAMBIO_TURNO" and "NOCTURNO" in just_txt):
                    turno_asignado_dia = "Nocturno"
                elif t_nov_type == "CAMBIO_TURNO_DIURNO" or (t_nov_type == "CAMBIO_TURNO" and "DIURNO" in just_txt):
                    turno_asignado_dia = "Diurno"

            es_turno_nocturno_fijo = "Nocturno" in turno_asignado_dia
            punches_dia = bio_by_emp_date.get((emp_id_str, fecha_dt), [])

            # --- CASO A: EMPLEADO TIENE MARCACIÓN ---
            if punches_dia:
                i = 0
                while i < len(punches_dia):
                    p_in = punches_dia[i]
                    dt_in = p_in['dt_parsed']
                    p_type = str(p_in.get(col_tipo, '')).strip().lower() if col_tipo else ''

                    dt_out = None
                    if 'salida' not in p_type:
                        j = i + 1
                        while j < len(punches_dia):
                            next_dt = punches_dia[j]['dt_parsed']
                            next_type = str(punches_dia[j].get(col_tipo, '')).strip().lower() if col_tipo else ''
                            
                            if (next_dt - dt_in).total_seconds() <= 16 * 3600:
                                if 'salida' in next_type or j == len(punches_dia) - 1 or (punches_dia[j+1]['dt_parsed'] - next_dt).total_seconds() > 4 * 3600:
                                    dt_out = next_dt
                                    i = j
                                    break
                            j += 1

                    hora_in_str = dt_in.strftime('%H:%M')
                    hora_out_str = dt_out.strftime('%H:%M') if dt_out else 'Falta Marcación'

                    es_ingreso_nocturno = (dt_in.hour >= 18 or dt_in.hour < 5)
                    es_nocturno = es_turno_nocturno_fijo or es_ingreso_nocturno
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

                    novedad_activa = None
                    exento_faltas = False
                    exento_atrasos = False

                    if nov_act:
                        novedad_activa = nov_act["tipo_novedad"]
                        if novedad_activa in ["BAJA_MEDICA", "PERMISO_CON_GOCE", "VACACIONES", "LICENCIA_MATERNIDAD", "LICENCIA_PATERNIDAD", "DUELO_FAMILIAR"]:
                            exento_faltas = True
                            exento_atrasos = True
                            atraso_minutos = 0
                        elif novedad_activa in ["PERMISO_SIN_GOCE", "FALTA_JUSTIFICADA"]:
                            exento_atrasos = True
                            atraso_minutos = 0
                        elif novedad_activa == "REDUCCION_LACTANCIA":
                            exento_atrasos = True
                            atraso_minutos = 0

                    turnos_computados = 1.0
                    horas_extras = 0.0
                    horas_nocturnas = horas_netas if es_nocturno else 0.0

                    if es_domingo:
                        if es_nocturno and dt_in.hour >= 18:
                            turnos_computados = 1.0
                            horas_extras = 0.0
                            if not novedad_activa:
                                novedad_activa = 'Inicio Semana Nocturna'
                        else:
                            turnos_computados = 1.5
                            if "Jornal" not in tipo_personal:
                                horas_extras = horas_netas
                            if not novedad_activa:
                                novedad_activa = 'Trabajo Domingo / Temporada Alta'
                    else:
                        if "Jornal" in tipo_personal:
                            turnos_computados = 1.5 if (es_nocturno and es_viernes) or horas_netas >= 11.5 else 1.0
                            horas_extras = 0.0
                        elif es_nocturno:
                            if es_viernes:
                                turnos_computados = 1.5
                                horas_extras = 0.0
                            else:
                                turnos_computados = 1.0
                                jornada_limite = 7.0
                                if horas_netas > jornada_limite:
                                    horas_extras = round(horas_netas - jornada_limite, 2)
                        else:
                            turnos_computados = 1.0
                            jornada_limite = 7.0 if novedad_activa == "REDUCCION_LACTANCIA" else 8.0
                            if horas_netas > jornada_limite:
                                horas_extras = round(horas_netas - jornada_limite, 2)

                    es_falta = (not dt_out) and not exento_faltas
                    
                    # Clasificación estricta de Falta con Marcación Incompleta
                    falta_justificada = 0
                    falta_injustificada = 0

                    if es_falta:
                        if novedad_activa in ["PERMISO_SIN_GOCE", "FALTA_JUSTIFICADA"]:
                            falta_justificada = 1
                        elif novedad_activa is None:
                            falta_injustificada = 1

                    desfase_ingreso = False
                    if horas_netas >= 7.0 and minutos_diferencia > 45 and not exento_atrasos:
                        desfase_ingreso = True

                    registros.append({
                        'Carnet_Identidad': emp_id_str,
                        'Nombre': emp_nombre,
                        'Tipo Personal': tipo_personal,
                        'Fecha': fecha_str,
                        'Día': dia_nombre_esp,
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
                        'Novedad / Licencia': novedad_activa if novedad_activa else 'Ninguna',
                        'Desfase Ingreso': desfase_ingreso,
                        'Estado': 'OK' if dt_out or exento_faltas else 'Revisar Marcación'
                    })
                    i += 1

            # --- CASO B: EMPLEADO NO TIENE MARCACIÓN ---
            else:
                novedad_activa = nov_act["tipo_novedad"] if nov_act else None

                falta_injustificada = 0
                falta_justificada = 0
                estado_registro = 'OK'

                # Licencias con Goce de Haber (Cobran 100% | No implican descuento | No son falta)
                es_licencia_pagada = novedad_activa in [
                    "BAJA_MEDICA", "PERMISO_CON_GOCE", "VACACIONES",
                    "LICENCIA_MATERNIDAD", "LICENCIA_PATERNIDAD", "DUELO_FAMILIAR"
                ]

                # Licencias Sin Goce de Haber (Descuento pero CANJEABLE)
                es_licencia_canjeable = novedad_activa in [
                    "PERMISO_SIN_GOCE", "FALTA_JUSTIFICADA"
                ]

                if es_licencia_pagada:
                    falta_justificada = 0
                    falta_injustificada = 0
                    estado_registro = f'Justificado ({novedad_activa})'
                elif es_licencia_canjeable:
                    falta_justificada = 1
                    falta_injustificada = 0
                    estado_registro = 'Permiso/Falta Justificada'
                else:
                    if es_domingo:
                        if es_turno_nocturno_fijo:
                            falta_injustificada = 1
                            estado_registro = 'Falta / Omisión Marcación'
                        else:
                            falta_injustificada = 0
                            estado_registro = 'Descanso Semanal'
                    elif es_sabado and es_turno_nocturno_fijo:
                        falta_injustificada = 0
                        estado_registro = 'Descanso Semanal'
                    else:
                        falta_injustificada = 1
                        estado_registro = 'Falta / Omisión Marcación'

                registros.append({
                    'Carnet_Identidad': emp_id_str,
                    'Nombre': emp_nombre,
                    'Tipo Personal': tipo_personal,
                    'Fecha': fecha_str,
                    'Día': dia_nombre_esp,
                    'Entrada': 'Sin Marcación',
                    'Salida': 'Sin Marcación',
                    'Horas Trabajadas': 0.0,
                    'Atraso (Minutos)': 0,
                    'Falta Justificada': falta_justificada,
                    'Falta Injustificada': falta_injustificada,
                    'Horas Extras': 0.0,
                    'Horas Nocturnas': 0.0,
                    'Turnos Computados': 0.0,
                    'Turno Dominante': turno_asignado_dia,
                    'Novedad / Licencia': novedad_activa if novedad_activa else ('Descanso Semanal' if estado_registro == 'Descanso Semanal' else 'Ninguna'),
                    'Desfase Ingreso': False,
                    'Estado': estado_registro
                })

    return pd.DataFrame(registros)


def detect_exceptions(df_resultado):
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    excepciones = []

    df_temp = df_resultado.copy()
    df_temp['dt_fecha'] = pd.to_datetime(df_temp['Fecha'])
    df_temp['Semana'] = df_temp['dt_fecha'].dt.isocalendar().week

    trabajados = df_temp[df_temp['Horas Trabajadas'] > 0]
    col_id_key = 'Carnet_Identidad' if 'Carnet_Identidad' in df_temp.columns else 'ID'
    
    dias_por_semana = trabajados.groupby([col_id_key, 'Semana'])['Fecha'].nunique().reset_index()
    semanas_7dias = set(
        dias_por_semana[dias_por_semana['Fecha'] >= 7].set_index([col_id_key, 'Semana']).index
    )

    for _, row in df_resultado.iterrows():
        emp_id = row.get('Carnet_Identidad', row.get('ID', ''))
        emp_nom = row['Nombre']
        fecha = row['Fecha']
        dt_f = pd.to_datetime(fecha)
        semana = dt_f.isocalendar().week

        if row['Estado'] in ['Revisar Marcación', 'Falta / Omisión Marcación'] and row['Falta Injustificada'] == 1:
            excepciones.append({
                'Carnet_Identidad': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': 'Falta / Omisión Marcación',
                'Detalle Excepción': f"Entrada: {row['Entrada']} | Salida: {row['Salida']}",
                'Valor a Revisar': '1 Falta a Procesar',
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'Injustificada',
                'Observaciones': ''
            })

        if row['Horas Extras'] > 0 or row.get('Novedad / Licencia') == 'Trabajo Domingo / Temporada Alta':
            detalle_txt = f"Trabajo Domingo: {row['Horas Trabajadas']} hrs" if row.get('Novedad / Licencia') == 'Trabajo Domingo / Temporada Alta' else f"Marcación excedente: {row['Horas Extras']} hrs"
            excepciones.append({
                'Carnet_Identidad': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': 'Horas Extras / Domingo',
                'Detalle Excepción': detalle_txt,
                'Valor a Revisar': f"{row['Horas Trabajadas'] if row['Horas Extras'] == 0 else row['Horas Extras']} hrs",
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': ''
            })

        if (emp_id, semana) in semanas_7dias:
            excepciones.append({
                'Carnet_Identidad': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': '7º Día Laborado',
                'Detalle Excepción': f"Empleado registró asistencia los 7 días de la semana {semana}",
                'Valor a Revisar': '1 Día Excedente',
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': ''
            })

        if row.get('Desfase Ingreso', False):
            excepciones.append({
                'Carnet_Identidad': emp_id,
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
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    resumen = []
    col_id_key = 'Carnet_Identidad' if 'Carnet_Identidad' in df_resultado.columns else 'ID'
    
    for (emp_id, emp_nom), grp in df_resultado.groupby([col_id_key, 'Nombre']):
        total_he = grp['Horas Extras'].sum()
        
        # REGLA CLAVE: Solo las Faltas Justificadas son canjeables
        # Las Faltas Injustificadas no entran a la bolsa de canje (se excluyen)
        total_faltas_canjeables = grp['Falta Justificada'].sum()
        
        turno_dom = grp['Turno Dominante'].mode()[0] if not grp['Turno Dominante'].empty else 'Diurno'
        costo_hora_dia = 7.0 if turno_dom == 'Nocturno' else 8.0

        dias_canjeables_max = int(total_he // costo_hora_dia)

        if total_he > 0 or total_faltas_canjeables > 0:
            resumen.append({
                'Carnet_Identidad': emp_id,
                'Nombre': emp_nom,
                'Turno Dominante': turno_dom,
                'Horas Costo por Día': costo_hora_dia,
                'Bolsa HE Acumulada (hrs)': round(total_he, 2),
                'Días Máx. Canjeables': dias_canjeables_max,
                'Faltas Registradas': int(total_faltas_canjeables),
                'Días a Canjear (Aplicar)': 0,
                'Estado Canje': 'Sin Aplicar'
            })

    return pd.DataFrame(resumen)
