import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any, Optional

TIPOS_NOVEDAD = [
    "BAJA_MEDICA",
    "PERMISO_CON_GOCE",
    "PERMISO_SIN_GOCE",
    "LICENCIA_MATERNIDAD",
    "REDUCCION_LACTANCIA",
    "VACACIONES",
    "LICENCIA_PATERNIDAD",
    "DUELO_FAMILIAR",
    "CAMBIO_TURNO",
    "CAMBIO_TURNO_NOCTURNO",
    "CAMBIO_TURNO_DIURNO"
]

class NovedadesManager:
    """
    Administración de Permisos, Bajas Médicas, Licencias, Reducción de Lactancia y Cambios de Turno
    vinculados por Carnet de Identidad (CI).
    """
    TIPOS_NOVEDAD = TIPOS_NOVEDAD

    def __init__(self, db_path: str = "novedades.db"):
        self.db_path = db_path
        self.TIPOS_NOVEDAD = TIPOS_NOVEDAD
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS novedades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    carnet_identidad TEXT NOT NULL,
                    empleado_nombre TEXT NOT NULL,
                    tipo_novedad TEXT NOT NULL,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT NOT NULL,
                    dias_totales INTEGER NOT NULL,
                    hora_entrada_proyectada TEXT,
                    hora_salida_proyectada TEXT,
                    justificacion TEXT,
                    registrado_por_pin TEXT NOT NULL,
                    fecha_registro TEXT NOT NULL
                )
            """)
            
            # Migración automática si la tabla ya existía sin las nuevas columnas
            cursor.execute("PRAGMA table_info(novedades)")
            columns = [col[1] for col in cursor.fetchall()]
            if "carnet_identidad" not in columns:
                cursor.execute("ALTER TABLE novedades ADD COLUMN carnet_identidad TEXT DEFAULT ''")
            if "hora_entrada_proyectada" not in columns:
                cursor.execute("ALTER TABLE novedades ADD COLUMN hora_entrada_proyectada TEXT")
            if "hora_salida_proyectada" not in columns:
                cursor.execute("ALTER TABLE novedades ADD COLUMN hora_salida_proyectada TEXT")
            
            conn.commit()

    def obtener_tipos_novedad(self) -> List[str]:
        return self.TIPOS_NOVEDAD

    def registrar_novedad(
        self,
        carnet_identidad: str,
        empleado_nombre: str,
        tipo_novedad: str,
        fecha_inicio: str,
        fecha_fin: str,
        justificacion: str,
        registrado_por_pin: str,
        hora_entrada_proyectada: Optional[str] = None,
        hora_salida_proyectada: Optional[str] = None
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
            ci_clean = str(carnet_identidad).strip()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO novedades 
                    (carnet_identidad, empleado_nombre, tipo_novedad, fecha_inicio, fecha_fin, dias_totales, 
                     hora_entrada_proyectada, hora_salida_proyectada, justificacion, registrado_por_pin, fecha_registro)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ci_clean, empleado_nombre, tipo_novedad, fecha_inicio, fecha_fin, dias_totales,
                      hora_entrada_proyectada, hora_salida_proyectada, justificacion, registrado_por_pin, fecha_registro))
                conn.commit()

            return {"exito": True, "mensaje": f"Novedad '{tipo_novedad}' registrada para CI {ci_clean} ({dias_totales} día(s))."}
        except Exception as e:
            return {"exito": False, "mensaje": f"Error al procesar la novedad: {str(e)}"}

    def evaluar_impacto_dia(self, carnet_identidad: str, fecha_str: str) -> Optional[Dict[str, Any]]:
        ci_clean = str(carnet_identidad).strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = cursor.execute("""
                SELECT * FROM novedades 
                WHERE (TRIM(carnet_identidad) = TRIM(?) OR LOWER(TRIM(empleado_nombre)) = LOWER(TRIM(?))) 
                  AND ? BETWEEN fecha_inicio AND fecha_fin
                ORDER BY id DESC LIMIT 1
            """, (ci_clean, ci_clean, fecha_str)).fetchone()
            if row:
                return dict(row)
        return None

    def obtener_todas_novedades(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute("SELECT * FROM novedades ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]
