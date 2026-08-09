from typing import Dict, Any, Optional, List
import pandas as pd
from modules.db_manager import DBManager

class AuditLogger:
    """
    Gestión centralizada de logs de auditoría para el sistema.
    Ahora usa Supabase (Opción A) manteniendo la misma interfaz pública.
    """

    def __init__(self):
        self.db = DBManager()

    def registrar_evento(
        self,
        usuario_pin: str,
        usuario_nombre: str,
        accion: str,
        modulo: str,
        detalles: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Registra un evento de auditoría en Supabase."""
        return self.db.registrar_evento(
            usuario_pin=usuario_pin,
            usuario_nombre=usuario_nombre,
            accion=accion,
            modulo=modulo,
            detalles=detalles
        )

    def obtener_logs(self, limite: int = 1000, *args, **kwargs) -> pd.DataFrame:
        """Devuelve los registros de auditoría estructurados en un DataFrame para Streamlit."""
        try:
            data = self.db.obtener_logs(limite=limite)
            if not data:
                return pd.DataFrame(columns=['Fecha y Hora', 'Usuario', 'Acción', 'Módulo', 'Detalles / Datos'])

            df = pd.DataFrame(data)
            # Adaptar nombres de columnas al formato que ya usaba la aplicación
            df = df.rename(columns={
                "timestamp": "Fecha y Hora",
                "usuario_nombre": "Usuario",
                "accion": "Acción",
                "modulo": "Módulo",
                "detalles": "Detalles / Datos"
            })
            # Seleccionar solo las columnas esperadas
            columnas = ['Fecha y Hora', 'Usuario', 'Acción', 'Módulo', 'Detalles / Datos']
            for col in columnas:
                if col not in df.columns:
                    df[col] = ""
            return df[columnas]
        except Exception:
            return pd.DataFrame(columns=['Fecha y Hora', 'Usuario', 'Acción', 'Módulo', 'Detalles / Datos'])
