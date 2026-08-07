import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd

class AuditLogger:
    """
    Gestión centralizada de logs de auditoría para el sistema.
    Registra todas las acciones críticas (Aprobaciones, Cierres, Novedades, Regularizaciones).
    """
    def __init__(self, db_path: str = "audit_log.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
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
        """Registra un evento de auditoría en la base de datos."""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            detalles_json = json.dumps(detalles, ensure_ascii=False) if detalles else "{}"

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_logs (timestamp, usuario_pin, usuario_nombre, accion, modulo, detalles)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (timestamp, usuario_pin, usuario_nombre, accion, modulo, detalles_json))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error al registrar log de auditoría: {e}")
            return False

    def obtener_logs(self, limite: int = 1000, *args, **kwargs) -> pd.DataFrame:
        """Devuelve los registros de auditoría estructurados en un DataFrame para Streamlit."""
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
            print(f"Error al obtener logs: {e}")
            return pd.DataFrame(columns=['Fecha y Hora', 'Usuario', 'Acción', 'Módulo', 'Detalles / Datos'])
