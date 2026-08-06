import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional, List

class LockManager:
    """
    Gestión de estado, decisiones de excepciones y cierre de períodos mensuales por colaborador.
    """
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_EN_PROCESO = "INICIAR APROBACIONES"
    ESTADO_FINALIZADO = "FINALIZADO"

    ROLES_SUPERUSUARIO = ["RESPONSABLE_OPERACIONES", "JEFE_PRODUCCION", "Jefe de Producción", "ADMINISTRADOR", "Responsable de Operaciones y Producción (Acceso Total)"]

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
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_period_locks (
                    periodo TEXT,
                    carnet_identidad TEXT,
                    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                    cerrado_por TEXT,
                    fecha_cierre TEXT,
                    motivo_reversion TEXT,
                    PRIMARY KEY (periodo, carnet_identidad)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exception_decisions (
                    periodo TEXT,
                    carnet_identidad TEXT,
                    fecha TEXT,
                    tipo_excepcion TEXT,
                    decision TEXT,
                    tipo_falta TEXT,
                    observaciones TEXT,
                    modificado_por TEXT,
                    fecha_modificacion TEXT,
                    PRIMARY KEY (periodo, carnet_identidad, fecha, tipo_excepcion)
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

    def es_editable(self, periodo: str, rol_usuario: str, ci_empleado: Optional[str] = None) -> bool:
        if "Acceso Total" in rol_usuario or rol_usuario in self.ROLES_SUPERUSUARIO:
            return True
            
        estado_gen = self.obtener_estado_periodo(periodo)
        if estado_gen == self.ESTADO_FINALIZADO:
            return False

        if ci_empleado:
            estado_emp = self.obtener_estado_empleado(periodo, ci_empleado)
            if estado_emp == self.ESTADO_FINALIZADO:
                return False

        return True

    def cambiar_estado(
        self,
        periodo: str,
        nuevo_estado: str,
        usuario_pin: str,
        rol_usuario: str,
        motivo: Optional[str] = None
    ) -> Dict[str, Any]:
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

    def obtener_estado_empleado(self, periodo: str, carnet_identidad: str) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            res = cursor.execute(
                "SELECT estado FROM employee_period_locks WHERE periodo = ? AND carnet_identidad = ?",
                (periodo, str(carnet_identidad).strip())
            ).fetchone()
            if res:
                return res[0]
        return self.ESTADO_PENDIENTE

    def cambiar_estado_empleado(
        self,
        periodo: str,
        carnet_identidad: str,
        nuevo_estado: str,
        usuario_pin: str,
        motivo: Optional[str] = None
    ) -> Dict[str, Any]:
        fecha_actual = datetime.now().isoformat()
        ci_clean = str(carnet_identidad).strip()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO employee_period_locks (periodo, carnet_identidad, estado, cerrado_por, fecha_cierre, motivo_reversion)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(periodo, carnet_identidad) DO UPDATE SET
                    estado = excluded.estado,
                    cerrado_por = excluded.cerrado_por,
                    fecha_cierre = excluded.fecha_cierre,
                    motivo_reversion = excluded.motivo_reversion
            """, (periodo, ci_clean, nuevo_estado, usuario_pin, fecha_actual, motivo or ""))
            conn.commit()
        return {"exito": True, "mensaje": f"Empleado CI {ci_clean} en período {periodo} actualizado a '{nuevo_estado}'."}

    def guardar_decisiones_excepciones(self, periodo: str, registros: List[Dict[str, Any]], usuario_pin: str):
        fecha_actual = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for reg in registros:
                ci = str(reg.get('Carnet_Identidad', '')).strip()
                fecha = str(reg.get('Fecha', '')).strip()
                tipo_exc = str(reg.get('Tipo Excepción', '')).strip()
                decision = str(reg.get('Decisión Supervisor', 'Pendiente')).strip()
                tipo_falta = str(reg.get('Tipo Falta', 'N/A')).strip()
                obs = str(reg.get('Observaciones', '')).strip()

                if ci and fecha and tipo_exc:
                    cursor.execute("""
                        INSERT INTO exception_decisions 
                        (periodo, carnet_identidad, fecha, tipo_excepcion, decision, tipo_falta, observaciones, modificado_por, fecha_modificacion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(periodo, carnet_identidad, fecha, tipo_excepcion) DO UPDATE SET
                            decision = excluded.decision,
                            tipo_falta = excluded.tipo_falta,
                            observaciones = excluded.observaciones,
                            modificado_por = excluded.modificado_por,
                            fecha_modificacion = excluded.fecha_modificacion
                    """, (periodo, ci, fecha, tipo_exc, decision, tipo_falta, obs, usuario_pin, fecha_actual))
            conn.commit()

    def obtener_decisiones_excepciones(self, periodo: str) -> Dict[tuple, Dict[str, str]]:
        """
        Devuelve el diccionario de decisiones tomadas para un período determinado.
        """
        decisiones = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT carnet_identidad, fecha, tipo_excepcion, decision, tipo_falta, observaciones FROM exception_decisions WHERE periodo = ?",
                (periodo,)
            ).fetchall()
            for r in rows:
                key = (str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip())
                decisiones[key] = {
                    "decision": r[3],
                    "tipo_falta": r[4],
                    "observaciones": r[5]
                }
        return decisiones
