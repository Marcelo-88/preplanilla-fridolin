import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

class LockManager:
    """
    Gestión de estado y cierre de períodos mensuales de asistencia.
    """
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_EN_PROCESO = "EN_PROCESO"
    ESTADO_FINALIZADO = "FINALIZADO"

    ROLES_SUPERUSUARIO = ["RESPONSABLE_OPERACIONES", "JEFE_PRODUCCION", "Jefe de Producción", "ADMINISTRADOR"]

    def __init__(self, db_path: str = "period_locks.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS period_locks (
                    periodo TEXT PRIMARY KEY,
                    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                    cerrado_por TEXT,
                    fecha_cierre TEXT,
                    motivo_desbloqueo TEXT
                )
            """)
            conn.commit()

    def obtener_estado_periodo(self, periodo: str) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            res = cursor.execute("SELECT estado FROM period_locks WHERE periodo = ?", (periodo,)).fetchone()
            if res:
                return res[0]
        return self.ESTADO_PENDIENTE

    def es_editable(self, periodo: str, rol_usuario: str) -> bool:
        estado = self.obtener_estado_periodo(periodo)
        if estado != self.ESTADO_FINALIZADO:
            return True
        return rol_usuario in self.ROLES_SUPERUSUARIO

    def cambiar_estado(
        self,
        periodo: str,
        nuevo_estado: str,
        usuario_pin: str,
        rol_usuario: str,
        motivo: Optional[str] = None
    ) -> Dict[str, Any]:
        if nuevo_estado not in [self.ESTADO_PENDIENTE, self.ESTADO_EN_PROCESO, self.ESTADO_FINALIZADO]:
            return {"exito": False, "mensaje": "Estado de período no válido."}

        estado_actual = self.obtener_estado_periodo(periodo)
        if estado_actual == self.ESTADO_FINALIZADO and nuevo_estado != self.ESTADO_FINALIZADO:
            if rol_usuario not in self.ROLES_SUPERUSUARIO:
                return {
                    "exito": False,
                    "mensaje": "Permiso denegado: Solo el Responsable de Operaciones o Jefe de Producción puede reabrir un período cerrado."
                }

        fecha_actual = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO period_locks (periodo, estado, cerrado_por, fecha_cierre, motivo_desbloqueo)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(periodo) DO UPDATE SET
                    estado = excluded.estado,
                    cerrado_por = excluded.cerrado_por,
                    fecha_cierre = excluded.fecha_cierre,
                    motivo_desbloqueo = excluded.motivo_desbloqueo
            """, (periodo, nuevo_estado, usuario_pin, fecha_actual, motivo or ""))
            conn.commit()

        return {"exito": True, "mensaje": f"Período {periodo} actualizado a estado '{nuevo_estado}'."}
