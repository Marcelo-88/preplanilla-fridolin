from typing import Dict, Any, Optional
from modules.db_manager import DBManager

class LockManager:
    """
    Gestión de estado y cierre de períodos mensuales de asistencia con autonomía por supervisor.
    Ahora usa Supabase (Opción A) manteniendo la misma interfaz pública.
    Clave de control: Periodo_Supervisor (ejemplo: 2026-07_CABRERA_YASMIN).
    """
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_EN_PROCESO = "EN_PROCESO"
    ESTADO_FINALIZADO = "FINALIZADO"

    ROLES_SUPERUSUARIO = ["RESPONSABLE_OPERACIONES", "JEFE_PRODUCCION", "Jefe de Producción", "ADMINISTRADOR"]

    def __init__(self):
        self.db = DBManager()

    def _construir_clave(self, periodo: str, usuario: Optional[str] = None) -> str:
        if usuario:
            usr_clean = str(usuario).strip().upper().replace(" ", "_")
            return f"{periodo}_{usr_clean}"
        return str(periodo)

    def obtener_estado_periodo(self, periodo: str, usuario: Optional[str] = None, *args, **kwargs) -> str:
        if not usuario and args:
            usuario = args[0]
        return self.db.obtener_estado_periodo(periodo, usuario)

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
        estado_actual = self.obtener_estado_periodo(periodo, usuario=usuario_ref)

        # Solo superusuarios pueden reabrir un período FINALIZADO
        if estado_actual == self.ESTADO_FINALIZADO and nuevo_estado != self.ESTADO_FINALIZADO:
            rol_clean = str(rol_usuario).strip().upper().replace(" ", "_")
            if rol_clean not in self.ROLES_SUPERUSUARIO and rol_usuario not in self.ROLES_SUPERUSUARIO:
                return {
                    "exito": False,
                    "mensaje": "Permiso denegado: Solo el Responsable de Operaciones o Jefe de Producción puede reabrir un período cerrado."
                }

        return self.db.cambiar_estado_periodo(
            periodo=periodo,
            nuevo_estado=nuevo_estado,
            usuario_pin=usuario_pin,
            usuario_nombre=usuario_ref,
            motivo=motivo
        )

    def exportar_respaldo_json(self) -> str:
        """Método mantenido por compatibilidad. Ya no es necesario con Supabase."""
        return "[]"

    def importar_respaldo_json(self, json_string: str) -> bool:
        """Método mantenido por compatibilidad. Ya no es necesario con Supabase."""
        return True
