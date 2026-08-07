import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

class LockManager:
    """
    Gestión de estado y cierre de períodos mensuales de asistencia con autonomía por supervisor.
    Clave de control: Periodo_Supervisor (ejemplo: 2026-07_CABRERA_YASMIN).
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

    def _construir_clave(self, periodo: str, usuario: Optional[str] = None) -> str:
        if usuario:
            usr_clean = str(usuario).strip().upper().replace(" ", "_")
            return f"{periodo}_{usr_clean}"
        return str(periodo)

    def obtener_estado_periodo(self, periodo: str, usuario: Optional[str] = None, *args, **kwargs) -> str:
        """
        Consulta el estado del período en la base de datos.
        Acepta tanto 'usuario' nombrado como parámetro posicional para compatibilidad estricta.
        """
        if not usuario and args:
            usuario = args[0]

        clave = self._construir_clave(periodo, usuario)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            res = cursor.execute("SELECT estado FROM period_locks WHERE periodo = ?", (clave,)).fetchone()
            if res:
                return res[0]
        return self.ESTADO_PENDIENTE

    def es_editable(self, periodo: str, rol_usuario: str, usuario: Optional[str] = None) -> bool:
        """
        Bloqueo estricto: La edición SOLO se habilita cuando el estado es 'EN_PROCESO'.
        Si está 'PENDIENTE', está bloqueado hasta presionar 'MARCAR EN PROCESO'.
        Si está 'FINALIZADO', solo los superusuarios pueden editar o desbloquear.
        """
        estado = self.obtener_estado_periodo(periodo, usuario=usuario)
        if estado == self.ESTADO_EN_PROCESO:
            return True
        if estado == self.ESTADO_FINALIZADO:
            rol_clean = str(rol_usuario).strip().upper().replace(" ", "_")
            return rol_clean in self.ROLES_SUPERUSUARIO or rol_usuario in self.ROLES_SUPERUSUARIO
        return False

    def cambiar_estado(
        self,
        periodo: str,
        nuevo_estado: str,
        usuario_pin: str,
        rol_usuario: str,
        usuario_nombre: Optional[str] = None,
        motivo: Optional[str] = None
    ) -> Dict[str, Any]:
        if nuevo_estado not in [self.ESTADO_PENDIENTE, self.ESTADO_EN_PROCESO, self.ESTADO_FINALIZADO]:
            return {"exito": False, "mensaje": "Estado de período no válido."}

        usuario_ref = usuario_nombre or usuario_pin
        clave = self._construir_clave(periodo, usuario_ref)

        estado_actual = self.obtener_estado_periodo(periodo, usuario=usuario_ref)
        if estado_actual == self.ESTADO_FINALIZADO and nuevo_estado != self.ESTADO_FINALIZADO:
            rol_clean = str(rol_usuario).strip().upper().replace(" ", "_")
            if rol_clean not in self.ROLES_SUPERUSUARIO and rol_usuario not in self.ROLES_SUPERUSUARIO:
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
            """, (clave, nuevo_estado, usuario_pin, fecha_actual, motivo or ""))
            conn.commit()

        return {"exito": True, "mensaje": f"Estado del período {periodo} para {usuario_ref} actualizado a '{nuevo_estado}'."}
