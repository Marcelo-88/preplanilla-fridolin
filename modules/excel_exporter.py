import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
from typing import List, Dict, Any

class ExcelExporter:
    """
    Exportador profesional de Pre-Planilla y Aprobaciones.
    """
    @staticmethod
    def exportar_preplanilla(
        datos_tabla: List[Dict[str, Any]],
        periodo: str,
        nombre_archivo: str = "PrePlanilla_Export.xlsx"
    ) -> str:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Pre-Planilla"
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
        fill_even = PatternFill(start_color="F9FBFD", end_color="F9FBFD", fill_type="solid")

        ws['A1'] = "REPORTE CONSOLIDADO DE PRE-PLANILLA"
        ws['A1'].font = title_font
        ws['A2'] = f"Período Evaluado: {periodo} | Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ws['A2'].font = subtitle_font

        ws.append([])

        if not datos_tabla:
            wb.save(nombre_archivo)
            return nombre_archivo

        headers = list(datos_tabla[0].keys())
        row_start = 4
        ws.append(headers)

        for col_num, h in enumerate(headers, 1):
            cell = ws.cell(row=row_start, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

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

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        wb.save(nombre_archivo)
        return nombre_archivo

    @staticmethod
    def exportar_aprobaciones(
        datos_tabla: List[Dict[str, Any]],
        periodo: str,
        nombre_archivo: str = "Aprobaciones_Export.xlsx"
    ) -> str:
        return ExcelExporter.exportar_preplanilla(datos_tabla, periodo, nombre_archivo)
