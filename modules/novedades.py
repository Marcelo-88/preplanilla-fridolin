import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any, Optional

class NovedadesManager:
    """
    Administración de Permisos, Bajas Médicas, Licencias y Reducción de Lactancia.
    """
    TIPOS_NOVEDAD = [
        "BAJA_MEDICA",
        "PERMISO_CON_GOCE",
        "PERMISO_SIN_GOCE",
        "LICENCIA_MATERNIDAD",
        "REDUCCION_LACTANCIA",
        "VACACIONES",
        "LICENCIA_PATERNIDAD",
        "DUELO_FAMILIAR"
    ]

    def __init__(self, db_path: str = "novedades.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS novedades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id TEXT NOT NULL,
                    empleado_nombre TEXT NOT NULL,
                    tipo_novedad TEXT NOT NULL,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT NOT NULL,
                    dias_totales INTEGER NOT NULL,
                    justificacion TEXT,
                    registrado_por_pin TEXT NOT NULL,
                    fecha_registro TEXT NOT NULL
                )
            """)
            conn.commit()

    def registrar_novedad(
        self,
        empleado_id: str,
        empleado_nombre: str,
        tipo_novedad: str,
        fecha_inicio: str,
        fecha_fin: str,
        justificacion: str,
        registrado_por_pin: str
    ) -> Dict[str, Any]:
        if tipo_novedad not in self.TIPOS_NOVEDAD:
            return {"exito": False, "mensaje": f"Tipo de novedad '{tipo_novedad}' no válido."}

        try:
            f_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
            f_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
            if f_fin < f_ini:
                return {"exito": False, "mensaje": "La fecha final no puede ser anterior a la de inicio."}

            dias_totales = (f_fin - f_ini).days + 1
            fecha_registro = datetime.now().isoformat()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO novedades 
                    (empleado_id, empleado_nombre, tipo_novedad, fecha_inicio, fecha_fin, dias_totales, justificacion, registrado_por_pin, fecha_registro)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (empleado_id, empleado_nombre, tipo_novedad, fecha_inicio, fecha_fin, dias_totales, justificacion, registrado_por_pin, fecha_registro))
                conn.commit()

            return {"exito": True, "mensaje": f"Novedad '{tipo_novedad}' registrada ({dias_totales} día(s))."}
        except Exception as e:
            return {"exito": False, "mensaje": f"Error al procesar la novedad: {str(e)}"}

    def evaluar_impacto_dia(self, empleado_id: str, fecha_str: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = cursor.execute("""
                SELECT * FROM novedades 
                WHERE (LOWER(TRIM(empleado_id)) = LOWER(TRIM(?)) OR LOWER(TRIM(empleado_nombre)) = LOWER(TRIM(?))) AND ? BETWEEN fecha_inicio AND fecha_fin
            """, (empleado_id, empleado_id, fecha_str)).fetchone()
            if row:
                return dict(row)
        return None

    def obtener_todas_novedades(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute("SELECT * FROM novedades ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]
