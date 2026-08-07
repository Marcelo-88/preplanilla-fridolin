import sqlite3
import json
from datetime import datetime
import pandas as pd
from typing import Dict, Any, Optional

class AuditLogger:
    """
    Gestor de la bitácora de auditoría e historial de cambios para la aplicación.
    Almacena eventos en una base de datos SQLite y genera reportes para Streamlit.
    """
    def __init__(self, db_path: str = "audit_log.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.cursor().execute("""
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        usuario_pin TEXT,
                        usuario_nombre TEXT,
                        accion TEXT NOT NULL,
                        modulo TEXT NOT NULL,
                        detalles TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            print(f"Error al inicializar tabla de auditoría: {e}")

    def registrar_evento(
        self, 
        usuario_pin: str, 
        usuario_nombre: str, 
        accion: str, 
        modulo: str, 
        detalles: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Registra un evento en la tabla de bitácora."""
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            det = json.dumps(detalles, ensure_ascii=False) if detalles else "{}"
            with sqlite3.connect(self.db_path) as conn:
                conn.cursor().execute(
                    """
                    INSERT INTO audit_logs (timestamp, usuario_pin, usuario_nombre, accion, modulo, detalles)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ts, usuario_pin, usuario_nombre, accion, modulo, det)
                )
                conn.commit()
            return True
        except Exception as e:
            print(f"Error al registrar evento: {e}")
            return False

    def obtener_logs(self, limite: int = 1000, *args, **kwargs) -> pd.DataFrame:
        """
        Consulta y retorna los últimos registros de la bitácora de auditoría.
        Acepta 'limite' e ignore cualquier parámetro extra para evitar AttributeError.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(
                    """
                    SELECT 
                        timestamp AS 'Fecha y Hora', 
                        usuario_nombre AS 'Usuario', 
                        accion AS 'Acción', 
                        modulo AS 'Módulo', 
                        detalles AS 'Detalles / Datos' 
                    FROM audit_logs 
                    ORDER BY id DESC 
                    LIMIT ?
                    """,
                    conn, 
                    params=(limite,)
                )
                return df
        except Exception as e:
            print(f"Error consultando logs: {e}")
            return pd.DataFrame(columns=['Fecha y Hora', 'Usuario', 'Acción', 'Módulo', 'Detalles / Datos'])
