import streamlit as st
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from modules.db_manager import DBManager

# Lista global a nivel de módulo (se mantiene igual)
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
    Administración de Permisos, Bajas Médicas, Licencias, Reducción de Lactancia y Cambios de Turno.
    Ahora usa Supabase (Opción A) manteniendo la misma interfaz pública.
    """
    TIPOS_NOVEDAD = TIPOS_NOVEDAD

    def __init__(self):
        self.db = DBManager()
        self.TIPOS_NOVEDAD = TIPOS_NOVEDAD

    def obtener_tipos_novedad(self) -> List[str]:
        """Retorna la lista oficial de tipos de novedad."""
        return self.TIPOS_NOVEDAD

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

            data = {
                "empleado_id": str(empleado_id).strip(),
                "empleado_nombre": str(empleado_nombre).strip(),
                "tipo_novedad": tipo_novedad,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
                "dias_totales": dias_totales,
                "justificacion": justificacion or "",
                "registrado_por_pin": str(registrado_por_pin)
            }

            resultado = self.db.registrar_novedad(data)
            return resultado

        except Exception as e:
            return {"exito": False, "mensaje": f"Error al procesar la novedad: {str(e)}"}

    def evaluar_impacto_dia(self, empleado_id: str, fecha_str: str) -> Optional[Dict[str, Any]]:
        """Evalúa si un empleado tiene una novedad activa en una fecha específica."""
        return self.db.evaluar_impacto_dia(str(empleado_id).strip(), fecha_str)

    def obtener_todas_novedades(self) -> List[Dict[str, Any]]:
        """Devuelve todas las novedades registradas (más recientes primero)."""
        return self.db.obtener_todas_novedades()
