import streamlit as st
from supabase import create_client, Client
from datetime import datetime
from typing import Dict, Any, List, Optional
import json

@st.cache_resource
def get_supabase_client() -> Client:
    """Crea y cachea el cliente de Supabase usando la service_role key."""
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["service_role_key"]
    return create_client(url, key)

class DBManager:
    """Capa de persistencia centralizada para Fridolin (Opción A - Supabase)."""

    def __init__(self):
        self.client = get_supabase_client()

    # ------------------------------------------------------------------
    # PERIOD LOCKS
    # ------------------------------------------------------------------
    def obtener_estado_periodo(self, periodo: str, usuario: Optional[str] = None) -> str:
        clave = f"{periodo}_{str(usuario).strip().upper().replace(' ', '_')}" if usuario else periodo
        try:
            res = self.client.table("period_locks").select("estado").eq("periodo", clave).execute()
            if res.data:
                return res.data[0]["estado"]
        except Exception:
            pass
        return "PENDIENTE"

    def cambiar_estado_periodo(
        self,
        periodo: str,
        nuevo_estado: str,
        usuario_pin: str,
        usuario_nombre: Optional[str] = None,
        motivo: Optional[str] = None
    ) -> Dict[str, Any]:
        usuario_ref = usuario_nombre or usuario_pin
        clave = f"{periodo}_{str(usuario_ref).strip().upper().replace(' ', '_')}"
        try:
            self.client.table("period_locks").upsert({
                "periodo": clave,
                "estado": nuevo_estado,
                "cerrado_por": usuario_pin,
                "fecha_cierre": datetime.now().isoformat(),
                "motivo_desbloqueo": motivo or ""
            }).execute()
            return {"exito": True, "mensaje": f"Estado actualizado a {nuevo_estado}"}
        except Exception as e:
            return {"exito": False, "mensaje": str(e)}

    # ------------------------------------------------------------------
    # NOVEDADES
    # ------------------------------------------------------------------
    def registrar_novedad(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.client.table("novedades").insert(data).execute()
            return {"exito": True, "mensaje": "Novedad registrada correctamente"}
        except Exception as e:
            return {"exito": False, "mensaje": str(e)}

    def obtener_todas_novedades(self) -> List[Dict[str, Any]]:
        try:
            res = self.client.table("novedades").select("*").order("id", desc=True).execute()
            return res.data or []
        except Exception:
            return []

    def evaluar_impacto_dia(self, empleado_id: str, fecha_str: str) -> Optional[Dict[str, Any]]:
        try:
            res = (
                self.client.table("novedades")
                .select("*")
                .eq("empleado_id", empleado_id)
                .lte("fecha_inicio", fecha_str)
                .gte("fecha_fin", fecha_str)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # AUDIT LOG
    # ------------------------------------------------------------------
    def registrar_evento(
        self,
        usuario_pin: str,
        usuario_nombre: str,
        accion: str,
        modulo: str,
        detalles: Optional[Dict[str, Any]] = None
    ) -> bool:
        try:
            self.client.table("audit_logs").insert({
                "usuario_pin": usuario_pin,
                "usuario_nombre": usuario_nombre,
                "accion": accion,
                "modulo": modulo,
                "detalles": detalles or {}
            }).execute()
            return True
        except Exception:
            return False

    def obtener_logs(self, limite: int = 500) -> List[Dict[str, Any]]:
        try:
            res = (
                self.client.table("audit_logs")
                .select("*")
                .order("id", desc=True)
                .limit(limite)
                .execute()
            )
            return res.data or []
        except Exception:
            return []
