import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
from typing import List, Dict, Any, Optional

from modules.tarifas_manager import obtener_tarifa_empleado


class ExcelExporter:
    
    @staticmethod
    def _aplicar_autoajuste(ws):
        """Ajusta automáticamente el ancho de las columnas."""
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if cell.number_format and 'Bs' in cell.number_format:
                    val_str += '    '
                max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    @staticmethod
    def _aplicar_estilo_hoja(ws, titulo: str, periodo: str, datos_tabla: List[Dict[str, Any]]):
        ws.views.sheetView[0].showGridLines = True

        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=15, bold=True, color="1F4E79")
        subtitle_font = Font(name="Calibri", size=10, italic=True, color="595959")
        
        border_thin = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )
        fill_even = PatternFill(start_color="F2F7FA", end_color="F2F7FA", fill_type="solid")

        ws['A1'] = titulo
        ws['A1'].font = title_font
        ws['A2'] = f"Período Evaluado: {periodo} | Exportado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ws['A2'].font = subtitle_font

        ws.append([])

        if not datos_tabla:
            ws.append(["Sin datos disponibles para el período seleccionado"])
            return

        headers = list(datos_tabla[0].keys())
        row_start = 4
        ws.append(headers)

        for col_num, h in enumerate(headers, 1):
            cell = ws.cell(row=row_start, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        current_row = row_start + 1
        for idx, item in enumerate(datos_tabla):
            row_data = [item.get(h, "") for h in headers]
            ws.append(row_data)

            is_even = idx % 2 == 0
            for col_num in range(1, len(headers) + 1):
                c = ws.cell(row=current_row, column=col_num)
                c.border = border_thin
                if is_even:
                    c.fill = fill_even
            current_row += 1

        ExcelExporter._aplicar_autoajuste(ws)

    @staticmethod
    def exportar_preplanilla_oficial(
        datos_asistencia: List[Dict[str, Any]],
        maestro_empleados: List[Dict[str, Any]],
        periodo: str,
        nombre_archivo: str = "PrePlanilla_Oficial_Fridolin.xlsx"
    ) -> str:
        """
        Genera la Pre-Planilla oficial de 3 pestañas:
        1. Fijos y Eventuales
        2. Jornaleros
        3. Bonos (Módulo Producción)
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active) # Eliminar pestaña por defecto

        # Diccionario auxiliar del Maestro de Empleados
        dict_maestro = {}
        for emp in maestro_empleados:
            ci = str(emp.get('Carnet_Identidad', '')).strip()
            if ci:
                dict_maestro[ci] = {
                    'Nombre_Completo': emp.get('Nombre_Completo', emp.get('Nombre', 'SIN NOMBRE')),
                    'Area_Sector': emp.get('Area_Departamento', emp.get('Area_Sector', 'FABRICA')),
                    'Cargo': emp.get('Rol', emp.get('Cargo', 'OPERARIO')),
                    'Centro_Costo': emp.get('Centro_Costo', 'FRIDOLIN'),
                    'Tipo_Personal': emp.get('Tipo_Personal', 'Fijo')
                }

        # Estilos generales
        font_titulo = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
        font_header_white = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_header_black = Font(name="Calibri", size=11, bold=True, color="000000")
        font_body = Font(name="Calibri", size=10)

        fill_azul = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        fill_verde = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        fill_rojo = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        fill_gris = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

        border_thin = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        # ==========================================
        # PESTAÑA 1: FIJOS Y EVENTUALES
        # ==========================================
        ws1 = wb.create_sheet(title="Fijos y Eventuales")
        ws1.views.sheetView[0].showGridLines = True

        ws1.merge_cells("A1:N1")
        ws1["A1"] = f"EMPRESA FRIDOLIN - PRE-PLANILLA DE ASISTENCIA ({periodo})"
        ws1["A1"].font = font_titulo
        ws1["A1"].fill = fill_azul
        ws1["A1"].alignment = align_center

        headers_p1 = [
            ("Nombre_Completo", fill_azul, font_header_white),
            ("Carnet_Identidad", fill_azul, font_header_white),
            ("Area_Sector", fill_azul, font_header_white),
            ("Cargo", fill_azul, font_header_white),
            ("Centro_Costo", fill_azul, font_header_white),
            ("DIAS_TRABAJADOS", fill_verde, font_header_black),
            ("HORAS_EXTRA", fill_verde, font_header_black),
            ("1/2 TURNOS", fill_verde, font_header_black),
            ("REC. NOCTURNO (hrs)", fill_verde, font_header_black),
            ("DOMINICALES", fill_verde, font_header_black),
            ("ATRASOS (min)", fill_rojo, font_header_black),
            ("FALTAS JUSTIFICADA", fill_rojo, font_header_black),
            ("FALTAS INJUSTIFICADA", fill_rojo, font_header_black),
            ("OBSERVACIONES", fill_gris, font_header_black)
        ]

        for col_idx, (h_name, fill_style, font_style) in enumerate(headers_p1, start=1):
            c = ws1.cell(row=3, column=col_idx, value=h_name)
            c.fill = fill_style
            c.font = font_style
            c.alignment = align_center
            c.border = border_thin

        # Agrupar datos por empleado
        grouped_emp = {}
        for reg in datos_asistencia:
            ci = str(reg.get('Carnet_Identidad', reg.get('ID', ''))).strip()
            if not ci:
                continue
            if ci not in grouped_emp:
                grouped_emp[ci] = []
            grouped_emp[ci].append(reg)

        row_idx = 4
        for ci, regs in grouped_emp.items():
            info_m = dict_maestro.get(ci, {
                'Nombre_Completo': regs[0].get('Nombre', 'DESCONOCIDO'),
                'Area_Sector': 'FABRICA',
                'Cargo': 'OPERARIO',
                'Centro_Costo': 'FRIDOLIN',
                'Tipo_Personal': 'Fijo'
            })

            # Excluir Jornaleros de Pestaña 1
            if str(info_m.get('Tipo_Personal', '')).strip().upper() == 'JORNALERO':
                continue

            dias_trab = len(regs)
            horas_extra = sum(float(r.get('Horas Extras', 0) or 0) for r in regs)
            medio_turnos = sum(float(r.get('1/2 Turnos', 0) or 0) for r in regs)
            rec_nocturno = sum(float(r.get('Horas Nocturnas', 0) or 0) for r in regs)
            dominicales = sum(1 for r in regs if r.get('Es Dominical', False))
            atrasos_min = sum(int(r.get('Atraso (Minutos)', 0) or 0) for r in regs)
            faltas_just = sum(int(r.get('Falta Justificada', 0) or 0) for r in regs)
            faltas_injust = sum(int(r.get('Falta Injustificada', 0) or 0) for r in regs)

            vals_1 = [
                info_m['Nombre_Completo'],
                ci,
                info_m['Area_Sector'],
                info_m['Cargo'],
                info_m['Centro_Costo'],
                dias_trab,
                horas_extra,
                medio_turnos,
                rec_nocturno,
                dominicales,
                atrasos_min,
                faltas_just,
                faltas_injust,
                ""
            ]

            for c_idx, val in enumerate(vals_1, start=1):
                cell = ws1.cell(row=row_idx, column=c_idx, value=val)
                cell.font = font_body
                cell.border = border_thin
                if c_idx in [1, 3, 4, 5]:
                    cell.alignment = align_left
                elif c_idx == 2:
                    cell.alignment = align_center
                else:
                    cell.alignment = align_right
                    if isinstance(val, float):
                        cell.number_format = '#,##0.00'

            row_idx += 1

        ExcelExporter._aplicar_autoajuste(ws1)

        # ==========================================
        # PESTAÑA 2: JORNALEROS
        # ==========================================
        ws2 = wb.create_sheet(title="Jornaleros")
        ws2.views.sheetView[0].showGridLines = True

        ws2.merge_cells("A1:K1")
        ws2["A1"] = f"EMPRESA FRIDOLIN - PLANILLA Y MONETIZACIÓN DE JORNALEROS ({periodo})"
        ws2["A1"].font = font_titulo
        ws2["A1"].fill = fill_azul
        ws2["A1"].alignment = align_center

        headers_p2 = [
            ("Nombre_Completo", fill_azul, font_header_white),
            ("Carnet_Identidad", fill_azul, font_header_white),
            ("Area_Sector", fill_azul, font_header_white),
            ("Diurno Normal 8h (Días)", fill_verde, font_header_black),
            ("Monto Diurno Normal (Bs)", fill_verde, font_header_black),
            ("Diurno 1.5 / 12h (Días)", fill_verde, font_header_black),
            ("Monto Diurno 1.5 (Bs)", fill_verde, font_header_black),
            ("Nocturno Normal 8h (Días)", fill_verde, font_header_black),
            ("Monto Nocturno Normal (Bs)", fill_verde, font_header_black),
            ("Nocturno 1.5 / 12h (Días)", fill_verde, font_header_black),
            ("TOTAL A PAGAR (Bs)", fill_verde, font_header_black)
        ]

        for col_idx, (h_name, fill_style, font_style) in enumerate(headers_p2, start=1):
            c = ws2.cell(row=3, column=col_idx, value=h_name)
            c.fill = fill_style
            c.font = font_style
            c.alignment = align_center
            c.border = border_thin

        row_idx_2 = 4
        for ci, regs in grouped_emp.items():
            info_m = dict_maestro.get(ci, {
                'Nombre_Completo': regs[0].get('Nombre', 'DESCONOCIDO'),
                'Area_Sector': 'FABRICA',
                'Tipo_Personal': 'Jornalero'
            })

            # Incluir solo Jornaleros (o todos si no se especificó)
            if str(info_m.get('Tipo_Personal', '')).strip().upper() != 'JORNALERO':
                continue

            # Conteo de turnos según tipo
            d_norm = sum(1 for r in regs if r.get('Turno Dominante') == 'Diurno' and float(r.get('Horas Trabajadas', 0) or 0) <= 9)
            d_15 = sum(1 for r in regs if r.get('Turno Dominante') == 'Diurno' and float(r.get('Horas Trabajadas', 0) or 0) > 9)
            n_norm = sum(1 for r in regs if r.get('Turno Dominante') == 'Nocturno' and float(r.get('Horas Trabajadas', 0) or 0) <= 8)
            n_15 = sum(1 for r in regs if r.get('Turno Dominante') == 'Nocturno' and float(r.get('Horas Trabajadas', 0) or 0) > 8)

            t_d_norm = obtener_tarifa_empleado(ci, "diurno_normal_8h")
            t_d_15 = obtener_tarifa_empleado(ci, "diurno_1_5_12h")
            t_n_norm = obtener_tarifa_empleado(ci, "nocturno_normal_8h")
            t_n_15 = obtener_tarifa_empleado(ci, "nocturno_1_5_12h")

            m_d_norm = d_norm * t_d_norm
            m_d_15 = d_15 * t_d_15
            m_n_norm = n_norm * t_n_norm
            m_n_15 = n_15 * t_n_15
            total_jornal = m_d_norm + m_d_15 + m_n_norm + m_n_15

            vals_2 = [
                info_m['Nombre_Completo'],
                ci,
                info_m['Area_Sector'],
                d_norm, m_d_norm,
                d_15, m_d_15,
                n_norm, m_n_norm,
                n_15,
                total_jornal
            ]

            for c_idx, val in enumerate(vals_2, start=1):
                cell = ws2.cell(row=row_idx_2, column=c_idx, value=val)
                cell.font = font_body
                cell.border = border_thin
                if c_idx in [1, 3]:
                    cell.alignment = align_left
                elif c_idx == 2:
                    cell.alignment = align_center
                else:
                    cell.alignment = align_right
                    if c_idx in [5, 7, 9, 11]:
                        cell.number_format = 'Bs#,##0.00'

            row_idx_2 += 1

        ExcelExporter._aplicar_autoajuste(ws2)

        # ==========================================
        # PESTAÑA 3: BONOS (MÓDULO PRODUCCIÓN)
        # ==========================================
        ws3 = wb.create_sheet(title="Bonos Producción")
        ws3.views.sheetView[0].showGridLines = True

        ws3.merge_cells("A1:G1")
        ws3["A1"] = f"EMPRESA FRIDOLIN - BONOS Y PRODUCCIÓN ADICIONAL ({periodo})"
        ws3["A1"].font = font_titulo
        ws3["A1"].fill = fill_azul
        ws3["A1"].alignment = align_center

        headers_p3 = [
            ("Nombre_Completo", fill_azul, font_header_white),
            ("Carnet_Identidad", fill_azul, font_header_white),
            ("Area_Sector", fill_azul, font_header_white),
            ("Produccion_Normal_Dia", fill_verde, font_header_black),
            ("Unidades_Adicionales", fill_verde, font_header_black),
            ("Monto_Bono_Unidad (Bs)", fill_verde, font_header_black),
            ("TOTAL_BONO_PRODUCCION (Bs)", fill_verde, font_header_black)
        ]

        for col_idx, (h_name, fill_style, font_style) in enumerate(headers_p3, start=1):
            c = ws3.cell(row=3, column=col_idx, value=h_name)
            c.fill = fill_style
            c.font = font_style
            c.alignment = align_center
            c.border = border_thin

        row_idx_3 = 4
        for ci, info_m in list(dict_maestro.items()):
            vals_3 = [
                info_m['Nombre_Completo'],
                ci,
                info_m['Area_Sector'],
                0, 0, 0.0, 0.0
            ]
            for c_idx, val in enumerate(vals_3, start=1):
                cell = ws3.cell(row=row_idx_3, column=c_idx, value=val)
                cell.font = font_body
                cell.border = border_thin
                if c_idx in [1, 3]:
                    cell.alignment = align_left
                elif c_idx == 2:
                    cell.alignment = align_center
                else:
                    cell.alignment = align_right
                    if c_idx in [6, 7]:
                        cell.number_format = 'Bs#,##0.00'

            row_idx_3 += 1

        ExcelExporter._aplicar_autoajuste(ws3)

        wb.save(nombre_archivo)
        return nombre_archivo

    @staticmethod
    def exportar_preplanilla(
        datos_tabla: List[Dict[str, Any]],
        periodo: str,
        nombre_archivo: str = "PrePlanilla_Export.xlsx"
    ) -> str:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Pre-Planilla"
        ExcelExporter._aplicar_estilo_hoja(ws, "REPORTE CONSOLIDADO DE PRE-PLANILLA DE ASISTENCIA", periodo, datos_tabla)
        wb.save(nombre_archivo)
        return nombre_archivo

    @staticmethod
    def exportar_aprobaciones(
        datos_excepciones: List[Dict[str, Any]],
        periodo: str,
        nombre_archivo: str = "Aprobaciones_Export.xlsx",
        datos_canje: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        wb = openpyxl.Workbook()
        
        ws_exc = wb.active
        ws_exc.title = "Excepciones Supervisores"
        ExcelExporter._aplicar_estilo_hoja(ws_exc, "CENTRO DE APROBACIONES Y EXCEPCIONES", periodo, datos_excepciones)

        if datos_canje:
            ws_canje = wb.create_sheet(title="Bolsa Canje HE")
            ExcelExporter._aplicar_estilo_hoja(ws_canje, "RESUMEN BOLSAS DE CANJE Y FALTAS", periodo, datos_canje)

        wb.save(nombre_archivo)
        return nombre_archivo
