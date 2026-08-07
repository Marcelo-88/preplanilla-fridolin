import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta

# Constantes de Parámetros Generales
TOLERANCIA_MINUTOS = 10
DESCUENTO_COMIDA_HORAS = 0.5  # 30 minutos obligatorios (almuerzo / cena)

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
    """Limpia cadenas, elimina espacios sobrantes y sufijos decimales innecesarios."""
    if pd.isna(val) or val is None:
        return ""
    txt = str(val).strip().upper()
    if txt.endswith('.0'):
        txt = txt[:-2]
    return txt


def process_attendance(df_bio, df_params=None, df_nov=None, df_emp=None, _nov_mgr=None):
    """
    Procesa el registro biométrico aplicando:
    1. Pareo dinámico continuo de 18 horas por empleado (Soporte Trasnoche +1 Día).
    2. Regla de Imputación Estricta al Día N de Entrada.
    3. Tolerancia de Atraso 'Todo o Nada' (<=10 min = 0; >=11 min = Cobro Completo).
    4. Truncamiento por defecto de Entradas Anticipadas y Salidas Tardías (>=30 min).
    5. Cómputos de Turno y Medio (1.5 Turnos) para jornadas nocturnas especiales (Dom/Vie).
    6. Excepciones e inmunidades para Personal STAFF.
    """
    if df_bio is None or df_bio.empty:
        return _empty_attendance_df()

    df = df_bio.copy()

    # 1. Identificación flexible de columnas en el Biométrico
    cols = {str(c).strip().lower(): c for c in df.columns}
    
    col_id = next((cols[k] for k in cols if any(x in k for x in ['id', 'carnet', 'ci', 'codigo'])), df.columns[0])
    col_nombre = next((cols[k] for k in cols if any(x in k for x in ['nombre', 'empleado', 'trabajador'])), df.columns[1] if len(df.columns) > 1 else col_id)
    col_fecha = next((cols[k] for k in cols if any(x in k for x in ['fecha', 'hora', 'marcacion', 'tiempo'])), df.columns[2] if len(df.columns) > 2 else col_id)
    col_tipo = next((cols[k] for k in cols if any(x in k for x in ['tipo', 'movimiento', 'evento', 'estado'])), None)

    # Parseo y ordenamiento cronológico por marcaciones
    df['dt_parsed'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['dt_parsed']).sort_values([col_id, 'dt_parsed']).reset_index(drop=True)

    if df.empty:
        return _empty_attendance_df()

    df['raw_id_clean'] = df[col_id].apply(clean_str)
    df['raw_nombre_clean'] = df[col_nombre].apply(clean_str) if col_nombre else df['raw_id_clean']

    # 2. Mapeo y Unificación con el Maestro de Empleados (Regla de Oro: CI)
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

        # Vinculación por CI o Nombre
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

    # Limpieza de Rebotador (Filtrar marcaciones repetidas < 2 minutos)
    df['prev_emp'] = df['emp_id_clean'].shift(1)
    df['prev_time'] = df['dt_parsed'].shift(1)
    df['diff_sec'] = (df['dt_parsed'] - df['prev_time']).dt.total_seconds()
    mask_rebotador = (df['emp_id_clean'] == df['prev_emp']) & (df['diff_sec'] < 120.0)
    df = df[~mask_rebotador].copy()

    # Pre-cargar Novedades y Permisos
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

    # Lista total de empleados y rango global de fechas
    emp_ids_bio = list(set(df['emp_id_clean'].unique()))
    emp_ids_master = list(dict_nombres_master.keys())
    todos_emp_ids = sorted(list(set(emp_ids_bio + emp_ids_master)))

    min_date = df['dt_parsed'].min().date()
    max_date = df['dt_parsed'].max().date()
    rango_dias = pd.date_range(min_date, max_date)

    bio_names_map = {}
    for row in df[['emp_id_clean', 'raw_nombre_clean']].drop_duplicates('emp_id_clean').to_dict('records'):
        bio_names_map[row['emp_id_clean']] = row['raw_nombre_clean']

    # 3. Algoritmo de Emparejamiento Dinámico (Ventana Flotante de 18 Horas)
    # Procesa todas las marcaciones continuas por empleado
    jornadas_procesadas = {} # Key: (emp_id, fecha_jornada) -> dict de jornada

    for emp_id_str, group in df.groupby('emp_id_clean'):
        punches = group.to_dict('records')
        n = len(punches)
        i = 0

        while i < n:
            p_curr = punches[i]
            dt_curr = p_curr['dt_parsed']
            p_type = str(p_curr.get(col_tipo, '')).strip().lower() if col_tipo else ''

            # Buscar salida dentro de la ventana continua de 18 horas
            dt_out = None
            idx_out = -1

            if 'salida' not in p_type:
                j = i + 1
                while j < n:
                    p_next = punches[j]
                    dt_next = p_next['dt_parsed']
                    diff_hours = (dt_next - dt_curr).total_seconds() / 3600.0

                    if diff_hours <= 18.0:
                        next_type = str(p_next.get(col_tipo, '')).strip().lower() if col_tipo else ''
                        if 'salida' in next_type or j == n - 1 or ((punches[j+1]['dt_parsed'] - dt_next).total_seconds() / 3600.0) > 4.0:
                            if diff_hours >= 0.25:  # Al menos 15 minutos de diferencia
                                dt_out = dt_next
                                idx_out = j
                                break
                    else:
                        break
                    j += 1

            # La jornada pertenece ESTRICTAMENTE a la fecha de la ENTRADA (Día N)
            fecha_jornada = dt_curr.date()

            if dt_out:
                jornadas_procesadas[(emp_id_str, fecha_jornada)] = {
                    'dt_in': dt_curr,
                    'dt_out': dt_out,
                    'estado_marcacion': 'OK'
                }
                i = idx_out + 1 if idx_out != -1 else i + 1
            else:
                # Marcación huérfana de entrada sin salida
                jornadas_procesadas[(emp_id_str, fecha_jornada)] = {
                    'dt_in': dt_curr,
                    'dt_out': None,
                    'estado_marcacion': 'Incompleto'
                }
                i += 1

    # 4. Construcción de Registros Finales por Empleado y Día de Calendario
    registros = []

    for emp_id_str in todos_emp_ids:
        emp_nombre = dict_nombres_master.get(emp_id_str) or bio_names_map.get(emp_id_str) or f"EMP-{emp_id_str}"
        tipo_personal = dict_tipo_personal.get(emp_id_str, "Fijo").strip()
        is_staff = "STAFF" in tipo_personal.upper()
        turno_asignado_base = dict_turno_personal.get(emp_id_str, "Diurno").capitalize()

        for single_date in rango_dias:
            fecha_dt = single_date.date()
            fecha_str = fecha_dt.strftime('%Y-%m-%d')
            dia_semana = fecha_dt.weekday()  # 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo
            dia_nombre_esp = DIAS_ESPANOL.get(dia_semana, fecha_dt.strftime('%A'))

            es_domingo = (dia_semana == 6)
            es_viernes = (dia_semana == 4)
            es_sabado = (dia_semana == 5)

            nov_act = obtener_novedad(emp_id_str, fecha_str)
            turno_asignado_dia = turno_asignado_base

            if nov_act:
                t_nov_type = str(nov_act.get("tipo_novedad", "")).upper()
                just_txt = str(nov_act.get("justificacion", "")).upper()

                if "NOCTURNO" in t_nov_type or "NOCTURNO" in just_txt:
                    turno_asignado_dia = "Nocturno"
                elif "DIURNO" in t_nov_type or "DIURNO" in just_txt:
                    turno_asignado_dia = "Diurno"

            jornada_info = jornadas_procesadas.get((emp_id_str, fecha_dt))

            # --- CASO A: TIENE JORNADA ASOCIADA AL DÍA N ---
            if jornada_info:
                dt_in = jornada_info['dt_in']
                dt_out = jornada_info['dt_out']

                hora_in_str = dt_in.strftime('%H:%M')
                hora_out_str = dt_out.strftime('%H:%M') if dt_out else 'Falta Marcación'

                # Determinación del Tipo de Turno Oficial Ejecutado
                # 1. Turno y Medio (Nocturno Especial): Entradas de 16:30 a 19:30 en Domingo o Viernes (soporta llegada anticipada)
                es_turno_y_medio = (es_domingo or es_viernes) and (time(16, 30) <= dt_in.time() <= time(19, 30))
                
                # 2. Turno Nocturno Ordinario: Entrada >= 20:00 o < 05:00 o Turno Fijo Nocturno
                es_nocturno_ordinario = not es_turno_y_medio and (
                    "Nocturno" in turno_asignado_dia or dt_in.hour >= 20 or dt_in.hour < 5
                )

                if es_turno_y_medio:
                    turno_label = 'Nocturno Especial (1.5 Turnos)'
                    hora_oficial_in = time(18, 0)
                    hora_oficial_out = time(5, 30)
                    jornada_horas_netas_std = 11.0
                    turnos_base = 1.5
                elif es_nocturno_ordinario:
                    turno_label = 'Nocturno'
                    hora_oficial_in = time(22, 0)
                    hora_oficial_out = time(5, 30)
                    jornada_horas_netas_std = 7.0
                    turnos_base = 1.0
                else:
                    turno_label = 'Diurno'
                    hora_oficial_in = time(7, 0)
                    hora_oficial_out = time(15, 30)
                    jornada_horas_netas_std = 8.0
                    turnos_base = 1.0

                # Cálculo de Tiempo Bruto y Neto
                if dt_out:
                    diff_bruta = (dt_out - dt_in).total_seconds() / 3600.0
                    if dt_out <= dt_in:
                        diff_bruta += 24.0
                    horas_brutas = max(0.0, diff_bruta)
                    horas_netas_reales = max(0.0, round(horas_brutas - DESCUENTO_COMIDA_HORAS, 2))
                else:
                    horas_brutas = 0.0
                    horas_netas_reales = 0.0

                # Regla de Truncamiento Implicito por Defecto (Entrada Anticipada / Salida Tardía)
                dt_oficial_in = datetime.combine(dt_in.date(), hora_oficial_in)
                dt_oficial_out = datetime.combine(
                    dt_in.date() + timedelta(days=1 if (es_nocturno_ordinario or es_turno_y_medio) else 0),
                    hora_oficial_out
                )

                # Banderas de Excepción (>= 30 min)
                entrada_anticipada_flag = False
                salida_tardia_flag = False

                if (dt_oficial_in - dt_in).total_seconds() / 60.0 >= 30.0:
                    entrada_anticipada_flag = True
                
                if dt_out and (dt_out - dt_oficial_out).total_seconds() / 60.0 >= 30.0:
                    salida_tardia_flag = True

                # Por defecto, la jornada se computa sobre el horario oficial truncado
                dt_effective_in = max(dt_in, dt_oficial_in)
                dt_effective_out = min(dt_out, dt_oficial_out) if dt_out else None

                if dt_effective_out and dt_effective_out > dt_effective_in:
                    horas_netas_truncadas = round(((dt_effective_out - dt_effective_in).total_seconds() / 3600.0) - DESCUENTO_COMIDA_HORAS, 2)
                    horas_netas_truncadas = max(0.0, horas_netas_truncadas)
                else:
                    horas_netas_truncadas = horas_netas_reales

                # Tolerancia de Atraso (Todo o Nada)
                minutos_diferencia = (dt_in - dt_oficial_in).total_seconds() / 60.0
                if minutos_diferencia <= TOLERANCIA_MINUTOS:
                    atraso_minutos = 0
                else:
                    atraso_minutos = int(minutos_diferencia)  # Cobro completo sin descuento

                # Novedades e Inmunidades
                novedad_activa = None
                exento_atrasos = False
                exento_faltas = False

                if nov_act:
                    novedad_activa = nov_act["tipo_novedad"]
                    if novedad_activa in ["BAJA_MEDICA", "PERMISO_CON_GOCE", "VACACIONES", "LICENCIA_MATERNIDAD", "LICENCIA_PATERNIDAD", "DUELO_FAMILIAR"]:
                        exento_faltas = True
                        exento_atrasos = True
                        atraso_minutos = 0
                    elif novedad_activa in ["PERMISO_SIN_GOCE", "FALTA_JUSTIFICADA", "REDUCCION_LACTANCIA"]:
                        exento_atrasos = True
                        atraso_minutos = 0

                # Aplicación Rígida para Personal STAFF
                he_informativa_staff = 0.0
                if is_staff:
                    atraso_minutos = 0
                    horas_extras = 0.0
                    turnos_computados = 1.0
                    if horas_netas_reales > jornada_horas_netas_std:
                        he_informativa_staff = round(horas_netas_reales - jornada_horas_netas_std, 2)
                else:
                    # Personal Operativo / Fijo / Jornal
                    turnos_computados = turnos_base if dt_out else 0.0
                    horas_extras = 0.0  # HE por defecto en 0.0 hasta ser aprobada la excepción si la hubiere

                horas_nocturnas = horas_netas_reales if (es_nocturno_ordinario or es_turno_y_medio) else 0.0

                es_falta = (not dt_out) and not exento_faltas
                falta_justificada = 0
                falta_injustificada = 1 if (es_falta and not is_staff) else 0

                desfase_ingreso = False
                if horas_netas_reales >= 7.0 and minutos_diferencia > 45 and not exento_atrasos:
                    desfase_ingreso = True

                estado_final = 'OK'
                if not dt_out:
                    estado_final = 'Revisar Marcación' if not exento_faltas else f'Justificado ({novedad_activa})'

                registros.append({
                    'Carnet_Identidad': emp_id_str,
                    'Nombre': emp_nombre,
                    'Tipo Personal': tipo_personal,
                    'Fecha': fecha_str,
                    'Día': dia_nombre_esp,
                    'Entrada': hora_in_str,
                    'Salida': hora_out_str,
                    'Horas Trabajadas': horas_netas_truncadas if not is_staff else horas_netas_reales,
                    'Atraso (Minutos)': atraso_minutos,
                    'Falta Justificada': falta_justificada,
                    'Falta Injustificada': falta_injustificada,
                    'Horas Extras': horas_extras,
                    'Horas Nocturnas': horas_nocturnas,
                    'Turnos Computados': turnos_computados,
                    'Turno Dominante': turno_label,
                    'Novedad / Licencia': novedad_activa if novedad_activa else 'Ninguna',
                    'Desfase Ingreso': desfase_ingreso,
                    'Entrada Anticipada Flag': entrada_anticipada_flag,
                    'Salida Tardia Flag': salida_tardia_flag,
                    'HE_Informativa_Staff': he_informativa_staff,
                    'Estado': estado_final
                })

            # --- CASO B: NO TIENE MARCACIÓN EN EL DÍA N ---
            else:
                novedad_activa = nov_act["tipo_novedad"] if nov_act else None

                falta_injustificada = 0
                falta_justificada = 0
                estado_registro = 'OK'

                es_licencia_pagada = novedad_activa in [
                    "BAJA_MEDICA", "PERMISO_CON_GOCE", "VACACIONES",
                    "LICENCIA_MATERNIDAD", "LICENCIA_PATERNIDAD", "DUELO_FAMILIAR"
                ]

                es_licencia_canjeable = novedad_activa in [
                    "PERMISO_SIN_GOCE", "FALTA_JUSTIFICADA"
                ]

                if is_staff:
                    falta_injustificada = 0
                    falta_justificada = 0
                    estado_registro = 'OK (STAFF)'
                elif es_licencia_pagada:
                    falta_justificada = 0
                    falta_injustificada = 0
                    estado_registro = f'Justificado ({novedad_activa})'
                elif es_licencia_canjeable:
                    falta_justificada = 1
                    falta_injustificada = 0
                    estado_registro = 'Permiso/Falta Justificada'
                else:
                    if es_domingo:
                        if "Nocturno" in turno_asignado_dia:
                            falta_injustificada = 1
                            estado_registro = 'Falta / Omisión Marcación'
                        else:
                            falta_injustificada = 0
                            estado_registro = 'Descanso Semanal'
                    elif es_sabado and "Nocturno" in turno_asignado_dia:
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
                    'Entrada Anticipada Flag': False,
                    'Salida Tardia Flag': False,
                    'HE_Informativa_Staff': 0.0,
                    'Estado': estado_registro
                })

    return pd.DataFrame(registros)


def detect_exceptions(df_resultado):
    """
    Detecta excepciones para la pantalla de Aprobaciones de Supervisores:
    1. Omisión de Marcación / Faltas Injustificadas.
    2. Entradas Anticipadas y Salidas Tardías (Excepción Pendiente >= 30 min).
    3. Solicitudes de Horas Extras y Domingos.
    4. 7º Día Laborado Continuo.
    5. Desfase Horario de Ingreso.
    """
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

        # 1. Omisión de Marcación
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

        # 2. Entradas Anticipadas y Salidas Tardías (Excepción Pendiente >= 30 min)
        if row.get('Entrada Anticipada Flag', False) or row.get('Salida Tardia Flag', False):
            motive = "Entrada Anticipada" if row.get('Entrada Anticipada Flag') else "Salida Tardía"
            excepciones.append({
                'Carnet_Identidad': emp_id,
                'Nombre': emp_nom,
                'Fecha': fecha,
                'Tipo Excepción': f'Excepción Pendiente ({motive})',
                'Detalle Excepción': f"Marcación fuera de horario oficial: Entrada {row['Entrada']} / Salida {row['Salida']}",
                'Valor a Revisar': f"{row['Horas Trabajadas']} hrs",
                'Decisión Supervisor': 'Pendiente',
                'Tipo Falta': 'N/A',
                'Observaciones': 'Requiere aprobación para recalcular HE o ingreso anticipado'
            })

        # 3. Horas Extras / Domingos
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

        # 4. 7º Día Laborado
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

        # 5. Desfase Horario de Ingreso
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
    """
    Genera el resumen acumulado para la Bolsa de Canjes (Horas Extras vs Faltas Justificadas).
    """
    if df_resultado is None or df_resultado.empty:
        return pd.DataFrame()

    resumen = []
    col_id_key = 'Carnet_Identidad' if 'Carnet_Identidad' in df_resultado.columns else 'ID'

    for (emp_id, emp_nom), grp in df_resultado.groupby([col_id_key, 'Nombre']):
        total_he = grp['Horas Extras'].sum()
        total_faltas_canjeables = grp['Falta Justificada'].sum()

        turno_dom = grp['Turno Dominante'].mode()[0] if not grp['Turno Dominante'].empty else 'Diurno'
        costo_hora_dia = 7.0 if "Nocturno" in str(turno_dom) else 8.0

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


def _empty_attendance_df():
    """Retorna la estructura base de DataFrame vacío para evitar errores de tipo."""
    return pd.DataFrame(columns=[
        'Carnet_Identidad', 'Nombre', 'Tipo Personal', 'Fecha', 'Día',
        'Entrada', 'Salida', 'Horas Trabajadas', 'Atraso (Minutos)',
        'Falta Justificada', 'Falta Injustificada', 'Horas Extras',
        'Horas Nocturnas', 'Turnos Computados', 'Turno Dominante',
        'Novedad / Licencia', 'Desfase Ingreso', 'Entrada Anticipada Flag',
        'Salida Tardia Flag', 'HE_Informativa_Staff', 'Estado'
    ])
