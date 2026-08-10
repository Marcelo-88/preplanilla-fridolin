import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta

TOLERANCIA_MINUTOS = 10
DESCUENTO_COMIDA_HORAS = 0.5

DIAS_ESPANOL = {
    0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves',
    4: 'Viernes', 5: 'Sábado', 6: 'Domingo'
}

def clean_str(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    txt = str(val).strip().upper()
    if txt.endswith('.0'):
        txt = txt[:-2]
    return txt


def process_attendance(df_bio, df_params=None, df_nov=None, df_emp=None, _nov_mgr=None):
    """
    Regla clave:
    - Sin entrada O sin salida → FALTA (atraso = 0)
    - Solo con entrada Y salida válidas se calcula atraso
    - La aprobación del supervisor puede corregir después
    """
    if df_bio is None or df_bio.empty:
        return _empty_attendance_df()

    df = df_bio.copy()
    cols = {str(c).strip().lower(): c for c in df.columns}

    col_id = next((cols[k] for k in cols if any(x in k for x in ['id', 'carnet', 'ci', 'codigo'])), df.columns[0])
    col_nombre = next((cols[k] for k in cols if any(x in k for x in ['nombre', 'empleado', 'trabajador'])), df.columns[1] if len(df.columns) > 1 else col_id)
    col_fecha = next((cols[k] for k in cols if any(x in k for x in ['fecha', 'hora', 'marcacion', 'tiempo'])), df.columns[2] if len(df.columns) > 2 else col_id)
    col_tipo = next((cols[k] for k in cols if any(x in k for x in ['tipo', 'movimiento', 'evento', 'estado'])), None)

    df['dt_parsed'] = pd.to_datetime(df[col_fecha], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['dt_parsed']).sort_values([col_id, 'dt_parsed']).reset_index(drop=True)
    if df.empty:
        return _empty_attendance_df()

    df['raw_id_clean'] = df[col_id].apply(clean_str)
    df['raw_nombre_clean'] = df[col_nombre].apply(clean_str) if col_nombre else df['raw_id_clean']

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

    df['emp_id_clean'] = df['raw_id_clean'].map(lambda x: mapping_bio_to_ci.get(x, x))

    df['prev_emp'] = df['emp_id_clean'].shift(1)
    df['prev_time'] = df['dt_parsed'].shift(1)
    df['diff_sec'] = (df['dt_parsed'] - df['prev_time']).dt.total_seconds()
    mask_rebotador = (df['emp_id_clean'] == df['prev_emp']) & (df['diff_sec'] < 120.0)
    df = df[~mask_rebotador].copy()

    nov_map = {}
    if _nov_mgr:
        try:
            todas_nov = _nov_mgr.obtener_todas_novedades()
            if isinstance(todas_nov, pd.DataFrame):
                todas_nov = todas_nov.to_dict('records')
            for n in (todas_nov or []):
                e_id = clean_str(n.get('empleado_id', n.get('carnet_identidad', '')))
                f_ini_str = str(n.get('fecha_inicio', ''))
                f_fin_str = str(n.get('fecha_fin', ''))
                t_nov = n.get('tipo_novedad', n.get('tipo', ''))
                just = n.get('justificacion', '')
                if e_id and f_ini_str and f_fin_str:
                    try:
                        d_start = datetime.strptime(f_ini_str[:10], '%Y-%m-%d').date()
                        d_end = datetime.strptime(f_fin_str[:10], '%Y-%m-%d').date()
                        curr = d_start
                        while curr <= d_end:
                            nov_map[(e_id, curr.strftime('%Y-%m-%d'))] = {"tipo_novedad": t_nov, "justificacion": just}
                            curr += timedelta(days=1)
                    except Exception:
                        pass
        except Exception:
            pass

    def obtener_novedad(e_id, f_str):
        return nov_map.get((e_id, f_str))

    emp_ids_bio = list(set(df['emp_id_clean'].unique()))
    emp_ids_master = list(dict_nombres_master.keys())
    todos_emp_ids = sorted(list(set(emp_ids_bio + emp_ids_master)))

    min_date = df['dt_parsed'].min().date()
    max_date = df['dt_parsed'].max().date()
    rango_dias = pd.date_range(min_date, max_date)

    bio_names_map = {}
    for row in df[['emp_id_clean', 'raw_nombre_clean']].drop_duplicates('emp_id_clean').to_dict('records'):
        bio_names_map[row['emp_id_clean']] = row['raw_nombre_clean']

    # Emparejamiento 18h
    jornadas_procesadas = {}
    for emp_id_str, group in df.groupby('emp_id_clean'):
        punches = group.to_dict('records')
        n = len(punches)
        i = 0
        while i < n:
            p_curr = punches[i]
            dt_curr = p_curr['dt_parsed']
            p_type = str(p_curr.get(col_tipo, '')).strip().lower() if col_tipo else ''

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
                        if 'salida' in next_type or j == n - 1 or ((punches[j+1]['dt_parsed'] - dt_next).total_seconds() / 3600.0 if j+1 < n else 99) > 4.0:
                            if diff_hours >= 0.25:
                                dt_out = dt_next
                                idx_out = j
                                break
                    else:
                        break
                    j += 1

            fecha_jornada = dt_curr.date()
            if dt_out:
                jornadas_procesadas[(emp_id_str, fecha_jornada)] = {
                    'dt_in': dt_curr, 'dt_out': dt_out, 'completo': True
                }
                i = idx_out + 1 if idx_out != -1 else i + 1
            else:
                jornadas_procesadas[(emp_id_str, fecha_jornada)] = {
                    'dt_in': dt_curr, 'dt_out': None, 'completo': False
                }
                i += 1

    registros = []

    for emp_id_str in todos_emp_ids:
        emp_nombre = dict_nombres_master.get(emp_id_str) or bio_names_map.get(emp_id_str) or f"EMP-{emp_id_str}"
        tipo_personal = dict_tipo_personal.get(emp_id_str, "Fijo").strip()
        is_staff = "STAFF" in tipo_personal.upper()
        turno_asignado_base = dict_turno_personal.get(emp_id_str, "Diurno").capitalize()
        if "nocturn" in turno_asignado_base.lower():
            turno_asignado_base = "Nocturno"
        else:
            turno_asignado_base = "Diurno"

        for single_date in rango_dias:
            fecha_dt = single_date.date()
            fecha_str = fecha_dt.strftime('%Y-%m-%d')
            dia_semana = fecha_dt.weekday()
            dia_nombre_esp = DIAS_ESPANOL.get(dia_semana, fecha_dt.strftime('%A'))
            es_domingo = (dia_semana == 6)
            es_viernes = (dia_semana == 4)
            es_sabado = (dia_semana == 5)

            nov_act = obtener_novedad(emp_id_str, fecha_str)
            turno_asignado_dia = turno_asignado_base
            if nov_act:
                t_nov = str(nov_act.get("tipo_novedad", "")).upper()
                just = str(nov_act.get("justificacion", "")).upper()
                if "NOCTURNO" in t_nov or "NOCTURNO" in just:
                    turno_asignado_dia = "Nocturno"
                elif "DIURNO" in t_nov or "DIURNO" in just:
                    turno_asignado_dia = "Diurno"

            jornada_info = jornadas_procesadas.get((emp_id_str, fecha_dt))
            es_personal_nocturno = (turno_asignado_dia == "Nocturno")

            # ----- SIN MARCACIÓN -----
            if not jornada_info:
                novedad_activa = str(nov_act.get("tipo_novedad", "")).upper() if nov_act else None
                falta_injustificada = 0
                falta_justificada = 0
                estado_registro = 'OK'

                es_licencia = novedad_activa in [
                    "BAJA_MEDICA", "PERMISO_CON_GOCE", "VACACIONES",
                    "LICENCIA_MATERNIDAD", "LICENCIA_PATERNIDAD", "DUELO_FAMILIAR",
                    "REDUCCION_LACTANCIA", "LACTANCIA", "MATERNIDAD"
                ]
                es_canjeable = novedad_activa in ["PERMISO_SIN_GOCE", "FALTA_JUSTIFICADA"]

                if is_staff:
                    estado_registro = 'OK (STAFF)'
                elif es_licencia:
                    estado_registro = f'Justificado ({novedad_activa})'
                elif es_canjeable:
                    falta_justificada = 1
                    estado_registro = 'Permiso/Falta Justificada'
                elif es_domingo and not es_personal_nocturno:
                    estado_registro = 'Descanso Semanal'
                elif es_sabado and es_personal_nocturno:
                    estado_registro = 'Descanso Semanal'
                else:
                    falta_injustificada = 1
                    estado_registro = 'Falta / Omisión Marcación'

                registros.append({
                    'Carnet_Identidad': emp_id_str, 'Nombre': emp_nombre, 'Tipo Personal': tipo_personal,
                    'Fecha': fecha_str, 'Día': dia_nombre_esp,
                    'Entrada': 'Sin Marcación', 'Salida': 'Sin Marcación',
                    'Horas Trabajadas': 0.0, 'Atraso (Minutos)': 0,
                    'Falta Justificada': falta_justificada, 'Falta Injustificada': falta_injustificada,
                    'Horas Extras': 0.0, 'Horas Nocturnas': 0.0, 'Turnos Computados': 0.0,
                    'Turno Dominante': turno_asignado_dia,
                    'Novedad / Licencia': novedad_activa or ('Descanso Semanal' if estado_registro == 'Descanso Semanal' else 'Ninguna'),
                    'Desfase Ingreso': False, 'Entrada Anticipada Flag': False, 'Salida Tardia Flag': False,
                    'HE_Informativa_Staff': 0.0, 'Estado': estado_registro, 'Anomalia Turno': False
                })
                continue

            # ----- CON MARCACIÓN -----
            dt_in = jornada_info['dt_in']
            dt_out = jornada_info['dt_out']
            completo = jornada_info.get('completo', False)

            # REGLA ESTRICTA: incompleto = FALTA, atraso = 0
            if not completo or dt_out is None:
                # Determinar si el punch único parece salida o entrada
                h = dt_in.hour + dt_in.minute / 60.0
                if not es_personal_nocturno and h >= 14.0:
                    hora_in_str = 'Sin Marcación'
                    hora_out_str = dt_in.strftime('%H:%M')
                else:
                    hora_in_str = dt_in.strftime('%H:%M')
                    hora_out_str = 'Falta Marcación'

                novedad_activa = str(nov_act.get("tipo_novedad", "")).upper() if nov_act else None
                exento = novedad_activa in [
                    "BAJA_MEDICA", "PERMISO_CON_GOCE", "VACACIONES",
                    "LICENCIA_MATERNIDAD", "LICENCIA_PATERNIDAD", "DUELO_FAMILIAR"
                ] if novedad_activa else False

                falta_injustificada = 0 if (is_staff or exento) else 1
                falta_justificada = 0

                registros.append({
                    'Carnet_Identidad': emp_id_str, 'Nombre': emp_nombre, 'Tipo Personal': tipo_personal,
                    'Fecha': fecha_str, 'Día': dia_nombre_esp,
                    'Entrada': hora_in_str, 'Salida': hora_out_str,
                    'Horas Trabajadas': 0.0,
                    'Atraso (Minutos)': 0,  # NUNCA atraso si falta entrada o salida
                    'Falta Justificada': falta_justificada,
                    'Falta Injustificada': falta_injustificada,
                    'Horas Extras': 0.0, 'Horas Nocturnas': 0.0, 'Turnos Computados': 0.0,
                    'Turno Dominante': turno_asignado_dia,
                    'Novedad / Licencia': novedad_activa or 'Ninguna',
                    'Desfase Ingreso': False, 'Entrada Anticipada Flag': False, 'Salida Tardia Flag': False,
                    'HE_Informativa_Staff': 0.0,
                    'Estado': 'Falta / Omisión Marcación',
                    'Anomalia Turno': False
                })
                continue

            # ----- JORNADA COMPLETA (entrada + salida) -----
            hora_in_str = dt_in.strftime('%H:%M')
            hora_out_str = dt_out.strftime('%H:%M')

            es_turno_y_medio = (
                es_personal_nocturno and (es_domingo or es_viernes) and
                (time(16, 0) <= dt_in.time() <= time(19, 30))
            )
            es_nocturno_ordinario = (
                es_personal_nocturno and not es_turno_y_medio and
                (dt_in.hour >= 20 or dt_in.hour < 5)
            )
            if not es_personal_nocturno:
                es_turno_y_medio = False
                es_nocturno_ordinario = False

            if es_turno_y_medio:
                turno_label = 'Nocturno Especial'
                hora_oficial_in = time(18, 0)
                hora_oficial_out = time(5, 30)
                jornada_std = 11.0
                turnos_base = 1.5
            elif es_nocturno_ordinario:
                turno_label = 'Nocturno'
                hora_oficial_in = time(22, 0)
                hora_oficial_out = time(5, 30)
                jornada_std = 7.0
                turnos_base = 1.0
            else:
                turno_label = 'Diurno'
                hora_oficial_in = time(7, 0)
                hora_oficial_out = time(15, 30)
                jornada_std = 8.0
                turnos_base = 1.0

            diff_bruta = (dt_out - dt_in).total_seconds() / 3600.0
            if dt_out <= dt_in:
                diff_bruta += 24.0
            horas_netas = max(0.0, round(diff_bruta - DESCUENTO_COMIDA_HORAS, 2))

            # Atraso SOLO con jornada completa
            dt_oficial_in = datetime.combine(dt_in.date(), hora_oficial_in)
            minutos_diff = (dt_in - dt_oficial_in).total_seconds() / 60.0
            atraso_minutos = int(minutos_diff) if minutos_diff > TOLERANCIA_MINUTOS else 0

            novedad_activa = str(nov_act.get("tipo_novedad", "")).upper() if nov_act else None
            if novedad_activa in ["BAJA_MEDICA", "PERMISO_CON_GOCE", "VACACIONES", "LICENCIA_MATERNIDAD", "LICENCIA_PATERNIDAD", "DUELO_FAMILIAR", "REDUCCION_LACTANCIA", "LACTANCIA", "MATERNIDAD"]:
                atraso_minutos = 0
                if novedad_activa in ["REDUCCION_LACTANCIA", "LACTANCIA", "MATERNIDAD"]:
                    jornada_std = 7.0

            if is_staff:
                atraso_minutos = 0

            entrada_anticipada = (dt_oficial_in - dt_in).total_seconds() / 60.0 >= 30
            dt_oficial_out = datetime.combine(
                dt_in.date() + timedelta(days=1 if (es_nocturno_ordinario or es_turno_y_medio) else 0),
                hora_oficial_out
            )
            salida_tardia = (dt_out - dt_oficial_out).total_seconds() / 60.0 >= 30

            desfase = atraso_minutos > 45
            anomalia = (not es_personal_nocturno and (dt_in.hour >= 16 or dt_in.hour < 5))

            registros.append({
                'Carnet_Identidad': emp_id_str, 'Nombre': emp_nombre, 'Tipo Personal': tipo_personal,
                'Fecha': fecha_str, 'Día': dia_nombre_esp,
                'Entrada': hora_in_str, 'Salida': hora_out_str,
                'Horas Trabajadas': horas_netas,
                'Atraso (Minutos)': atraso_minutos,
                'Falta Justificada': 0, 'Falta Injustificada': 0,
                'Horas Extras': 0.0,
                'Horas Nocturnas': horas_netas if (es_nocturno_ordinario or es_turno_y_medio) else 0.0,
                'Turnos Computados': turnos_base,
                'Turno Dominante': turno_label,
                'Novedad / Licencia': novedad_activa or 'Ninguna',
                'Desfase Ingreso': desfase,
                'Entrada Anticipada Flag': entrada_anticipada,
                'Salida Tardia Flag': salida_tardia,
                'HE_Informativa_Staff': 0.0,
                'Estado': 'Anomalía Turno' if anomalia else 'OK',
                'Anomalia Turno': anomalia
            })

    return pd.DataFrame(registros)


def _empty_attendance_df():
    return pd.DataFrame(columns=[
        'Carnet_Identidad', 'Nombre', 'Tipo Personal', 'Fecha', 'Día',
        'Entrada', 'Salida', 'Horas Trabajadas', 'Atraso (Minutos)',
        'Falta Justificada', 'Falta Injustificada', 'Horas Extras',
        'Horas Nocturnas', 'Turnos Computados', 'Turno Dominante',
        'Novedad / Licencia', 'Desfase Ingreso', 'Entrada Anticipada Flag',
        'Salida Tardia Flag', 'HE_Informativa_Staff', 'Estado', 'Anomalia Turno'
    ])


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
        semana = pd.to_datetime(fecha).isocalendar().week

        if row['Estado'] == 'Falta / Omisión Marcación' and row.get('Falta Injustificada', 0) == 1:
            excepciones.append({
                'Carnet_Identidad': emp_id, 'Nombre': emp_nom, 'Fecha': fecha,
                'Tipo Excepción': 'Falta / Omisión Marcación',
                'Detalle Excepción': f"Entrada: {row['Entrada']} | Salida: {row['Salida']}",
                'Valor a Revisar': '1 Falta a Procesar',
                'Decisión Supervisor': 'Pendiente', 'Tipo Falta': 'Injustificada', 'Observaciones': ''
            })

        if row.get('Anomalia Turno', False):
            excepciones.append({
                'Carnet_Identidad': emp_id, 'Nombre': emp_nom, 'Fecha': fecha,
                'Tipo Excepción': 'Anomalía Turno (Diurno en nocturno)',
                'Detalle Excepción': f"Personal Diurno marcó a las {row['Entrada']}",
                'Valor a Revisar': f"{row['Horas Trabajadas']} hrs",
                'Decisión Supervisor': 'Pendiente', 'Tipo Falta': 'N/A',
                'Observaciones': 'Requiere autorización'
            })

        if row.get('Entrada Anticipada Flag') or row.get('Salida Tardia Flag'):
            motive = "Entrada Anticipada" if row.get('Entrada Anticipada Flag') else "Salida Tardía"
            excepciones.append({
                'Carnet_Identidad': emp_id, 'Nombre': emp_nom, 'Fecha': fecha,
                'Tipo Excepción': f'Excepción Pendiente ({motive})',
                'Detalle Excepción': f"Entrada {row['Entrada']} / Salida {row['Salida']}",
                'Valor a Revisar': f"{row['Horas Trabajadas']} hrs",
                'Decisión Supervisor': 'Pendiente', 'Tipo Falta': 'N/A',
                'Observaciones': 'Requiere aprobación HE'
            })

        if (emp_id, semana) in semanas_7dias:
            excepciones.append({
                'Carnet_Identidad': emp_id, 'Nombre': emp_nom, 'Fecha': fecha,
                'Tipo Excepción': '7º Día Laborado',
                'Detalle Excepción': f"7 días en semana {semana}",
                'Valor a Revisar': '1 Día Excedente',
                'Decisión Supervisor': 'Pendiente', 'Tipo Falta': 'N/A', 'Observaciones': ''
            })

        if row.get('Desfase Ingreso', False):
            excepciones.append({
                'Carnet_Identidad': emp_id, 'Nombre': emp_nom, 'Fecha': fecha,
                'Tipo Excepción': 'Desfase Horario Ingreso',
                'Detalle Excepción': f"Ingresó a las {row['Entrada']} ({row.get('Atraso (Minutos)', 0)} min)",
                'Valor a Revisar': f"{row.get('Atraso (Minutos)', 0)} min",
                'Decisión Supervisor': 'Pendiente', 'Tipo Falta': 'N/A',
                'Observaciones': 'Entrada tardía con jornada completa'
            })

    return pd.DataFrame(excepciones)
