import os
import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

class LockManager:
    """
    Gestión de estado y cierre de períodos mensuales de asistencia con autonomía por supervisor.
    Clave de control: Periodo_Supervisor (ejemplo: 2026-07_CABRERA_YASMIN).
    Soporta sincronización y respaldo en JSON para servidores efímeros (Streamlit Cloud).
    """
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_EN_PROCESO = "EN_PROCESO"
    ESTADO_FINALIZADO = "FINALIZADO"

    ROLES_SUPERUSUARIO = ["RESPONSABLE_OPERACIONES", "JEFE_PRODUCCION", "Jefe de Producción", "ADMINISTRADOR"]

    def __init__(self, db_path: str = "period_locks.db", json_path: str = "period_locks_backup.json"):
        self.db_path = db_path
        self.json_path = json_path
        self._init_db()
        self._sincronizar_desde_json()

    def _init_db(self):
        try:
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
        except Exception as e:
            print(f"Error inicializando DB LockManager: {e}")

    def _construir_clave(self, periodo: str, usuario: Optional[str] = None) -> str:
        if usuario:
            usr_clean = str(usuario).strip().upper().replace(" ", "_")
            return f"{periodo}_{usr_clean}"
        return str(periodo)

    def _guardar_json_local(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.cursor().execute("SELECT * FROM period_locks").fetchall()
                data = [dict(r) for r in rows]
                
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error respaldando a JSON: {e}")

    def _sincronizar_desde_json(self):
        if not os.path.exists(self.json_path):
            return
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for reg in data:
                    cursor.execute("""
                        INSERT INTO period_locks (periodo, estado, cerrado_por, fecha_cierre, motivo_desbloqueo)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(periodo) DO UPDATE SET
                            estado = excluded.estado,
                            cerrado_por = excluded.cerrado_por,
                            fecha_cierre = excluded.fecha_cierre,
                            motivo_desbloqueo = excluded.motivo_desbloqueo
                    """, (reg["periodo"], reg["estado"], reg.get("cerrado_por", ""), reg.get("fecha_cierre", ""), reg.get("motivo_desbloqueo", "")))
                conn.commit()
        except Exception as e:
            print(f"Error restaurando desde JSON: {e}")

    def obtener_estado_periodo(self, periodo: str, usuario: Optional[str] = None, *args, **kwargs) -> str:
        if not usuario and args:
            usuario = args[0]

        clave = self._construir_clave(periodo, usuario)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                res = cursor.execute("SELECT estado FROM period_locks WHERE periodo = ?", (clave,)).fetchone()
                if res:
                    return res[0]
        except Exception:
            pass
        return self.ESTADO_PENDIENTE

    def es_editable(self, periodo: str, rol_usuario: str, usuario: Optional[str] = None) -> bool:
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
        try:
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

            self._guardar_json_local()
            return {"exito": True, "mensaje": f"Estado del período {periodo} para {usuario_ref} actualizado a '{nuevo_estado}'."}
        except Exception as e:
            return {"exito": False, "mensaje": f"Error actualizando estado en base de datos: {e}"}

    def exportar_respaldo_json(self) -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.cursor().execute("SELECT * FROM period_locks").fetchall()
                return json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2)
        except Exception:
            if os.path.exists(self.json_path):
                with open(self.json_path, "r", encoding="utf-8") as f:
                    return f.read()
            return "[]"

    def importar_respaldo_json(self, json_string: str) -> bool:
        try:
            data = json.loads(json_string)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for reg in data:
                    cursor.execute("""
                        INSERT INTO period_locks (periodo, estado, cerrado_por, fecha_cierre, motivo_desbloqueo)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(periodo) DO UPDATE SET
                            estado = excluded.estado,
                            cerrado_por = excluded.cerrado_por,
                            fecha_cierre = excluded.fecha_cierre,
                            motivo_desbloqueo = excluded.motivo_desbloqueo
                    """, (reg["periodo"], reg["estado"], reg.get("cerrado_por", ""), reg.get("fecha_cierre", ""), reg.get("motivo_desbloqueo", "")))
                conn.commit()
            self._guardar_json_local()
            return True
        except Exception:
            return False
