import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any

class AuditLogger:
    """
    Módulo de auditoría y bitácora de acciones críticas del sistema.
    """
    def __init__(self, db_path: str = "audit_log.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    usuario_pin TEXT NOT NULL,
                    usuario_nombre TEXT,
                    accion TEXT NOT NULL,
                    modulo TEXT NOT NULL,
                    detalles TEXT,
                    ip_address TEXT
                )
            """)
            conn.commit()

    def registrar_evento(
        self,
        usuario_pin: str,
        usuario_nombre: str,
        accion: str,
        modulo: str,
        detalles: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = "127.0.0.1"
    ) -> bool:
        try:
            timestamp = datetime.now().isoformat()
            detalles_str = json.dumps(detalles, ensure_ascii=False) if detalles else "{}"
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_logs (timestamp, usuario_pin, usuario_nombre, accion, modulo, detalles, ip_address)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (timestamp, usuario_pin, usuario_nombre, accion, modulo, detalles_str, ip_address))
                conn.commit()
            return True
        except Exception as e:
            print(f"[ERROR AuditLogger] No se pudo registrar evento: {e}")
            return False

    def obtener_historial(
        self,
        modulo: Optional[str] = None,
        usuario_pin: Optional[str] = None,
        limite: int = 100
    ) -> List[Dict[str, Any]]:
        query = "SELECT id, timestamp, usuario_pin, usuario_nombre, accion, modulo, detalles, ip_address FROM audit_logs"
        conditions = []
        params = []

        if modulo:
            conditions.append("modulo = ?")
            params.append(modulo)
        if usuario_pin:
            conditions.append("usuario_pin = ?")
            params.append(usuario_pin)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limite)

        logs = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute(query, params).fetchall()
            for r in rows:
                item = dict(r)
                item['detalles'] = json.loads(item['detalles']) if item['detalles'] else {}
                logs.append(item)
        return logs
