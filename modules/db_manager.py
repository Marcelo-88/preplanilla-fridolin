import streamlit as st
import httpx
from datetime import datetime
from typing import Dict, Any, List, Optional

class DBManager:
    """Capa de persistencia usando llamadas HTTP directas a Supabase."""

    def __init__(self):
        self.url = st.secrets["supabase"]["url"].rstrip("/")
        self.key = st.secrets["supabase"]["service_role_key"]
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def _request(self, method: str, path: str, json_data: dict = None, params: dict = None):
        full_url = f"{self.url}/rest/v1/{path}"
        try:
            with httpx.Client(timeout=20.0) as client:
                if method == "GET":
                    r = client.get(full_url, headers=self.headers, params=params)
                elif method == "POST":
                    r = client.post(full_url, headers=self.headers, json=json_data)
                elif method == "PATCH":
                    r = client.patch(full_url, headers=self.headers, json=json_data, params=params)
                else:
                    raise ValueError("Método no soportado")
                
                if r.status_code >= 400:
                    return {"error": f"HTTP {r.status_code}: {r.text}"}
                return r.json() if r.text else []
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # PERIOD LOCKS
    # ------------------------------------------------------------------
    def obtener_estado_periodo(self, periodo: str, usuario: Optional[str] = None) -> str:
        clave = f"{periodo}_{str(usuario).strip().upper().replace(' ', '_')}" if usuario else periodo
        res = self._request("GET", "period_locks", params={"periodo": f"eq.{clave}", "select": "estado"})
        if isinstance(res, list) and len(res) > 0:
            return res[0].get("estado", "PENDIENTE")
        return "PENDIENTE"

    def cambiar_estado_periodo(self, periodo: str, nuevo_estado: str, usuario_pin: str,
                               usuario_nombre: Optional[str] = None, motivo: Optional[str] = None) -> Dict[str, Any]:
        usuario_ref = usuario_nombre or usuario_pin
        clave = f"{periodo}_{str(usuario_ref).strip().upper().replace(' ', '_')}"
        data = {
            "periodo": clave,
            "estado": nuevo_estado,
            "cerrado_por": usuario_pin,
            "fecha_cierre": datetime.now().isoformat(),
            "motivo_desbloqueo": motivo or ""
        }
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=merge-duplicates,return=representation"
        full_url = f"{self.url}/rest/v1/period_locks?on_conflict=periodo"
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.post(full_url, headers=headers_upsert, json=data)
                if r.status_code >= 400:
                    return {"exito": False, "mensaje": f"Error HTTP {r.status_code}: {r.text}"}
                return {"exito": True, "mensaje": f"Estado actualizado a {nuevo_estado}"}
        except Exception as e:
            return {"exito": False, "mensaje": str(e)}

    # ------------------------------------------------------------------
    # NOVEDADES
    # ------------------------------------------------------------------
    def registrar_novedad(self, data: Dict[str, Any]) -> Dict[str, Any]:
        res = self._request("POST", "novedades", json_data=data)
        if isinstance(res, dict) and "error" in res:
            return {"exito": False, "mensaje": res["error"]}
        return {"exito": True, "mensaje": "Novedad registrada correctamente"}

    def obtener_todas_novedades(self) -> List[Dict[str, Any]]:
        res = self._request("GET", "novedades", params={"select": "*", "order": "id.desc"})
        return res if isinstance(res, list) else []

    def evaluar_impacto_dia(self, empleado_id: str, fecha_str: str) -> Optional[Dict[str, Any]]:
        params = {
            "empleado_id": f"eq.{empleado_id}",
            "fecha_inicio": f"lte.{fecha_str}",
            "fecha_fin": f"gte.{fecha_str}",
            "select": "*",
            "limit": "1"
        }
        res = self._request("GET", "novedades", params=params)
        if isinstance(res, list) and len(res) > 0:
            return res[0]
        return None

    # ------------------------------------------------------------------
    # AUDIT LOG
    # ------------------------------------------------------------------
    def registrar_evento(self, usuario_pin: str, usuario_nombre: str, accion: str,
                         modulo: str, detalles: Optional[Dict[str, Any]] = None) -> bool:
        data = {
            "usuario_pin": usuario_pin,
            "usuario_nombre": usuario_nombre,
            "accion": accion,
            "modulo": modulo,
            "detalles": detalles or {}
        }
        res = self._request("POST", "audit_logs", json_data=data)
        return not (isinstance(res, dict) and "error" in res)

    def obtener_logs(self, limite: int = 500) -> List[Dict[str, Any]]:
        res = self._request("GET", "audit_logs", params={"select": "*", "order": "id.desc", "limit": str(limite)})
        return res if isinstance(res, list) else []

    # ------------------------------------------------------------------
    # DECISIONES DEL SUPERVISOR (UPSERT CORREGIDO)
    # ------------------------------------------------------------------
    def guardar_decision(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Guarda o actualiza una decisión (upsert real)."""
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=merge-duplicates,return=representation"
        
        # on_conflict con las columnas de la unique constraint
        full_url = f"{self.url}/rest/v1/decisiones_supervisor?on_conflict=periodo,carnet_identidad,fecha,tipo_excepcion"
        
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.post(full_url, headers=headers_upsert, json=data)
                if r.status_code >= 400:
                    return {"exito": False, "mensaje": f"Error HTTP {r.status_code}: {r.text}"}
                return {"exito": True, "mensaje": "Decisión guardada/actualizada"}
        except Exception as e:
            return {"exito": False, "mensaje": str(e)}

    def obtener_decisiones_periodo(self, periodo: str) -> List[Dict[str, Any]]:
        res = self._request("GET", "decisiones_supervisor", params={"periodo": f"eq.{periodo}", "select": "*"})
        return res if isinstance(res, list) else []

    # ------------------------------------------------------------------
    # CANJES
    # ------------------------------------------------------------------
    def guardar_canje(self, data: Dict[str, Any]) -> Dict[str, Any]:
        headers_upsert = self.headers.copy()
        headers_upsert["Prefer"] = "resolution=merge-duplicates,return=representation"
        full_url = f"{self.url}/rest/v1/canjes?on_conflict=periodo,carnet_identidad"
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.post(full_url, headers=headers_upsert, json=data)
                if r.status_code >= 400:
                    return {"exito": False, "mensaje": f"Error HTTP {r.status_code}: {r.text}"}
                return {"exito": True, "mensaje": "Canje guardado"}
        except Exception as e:
            return {"exito": False, "mensaje": str(e)}

    def obtener_canjes_periodo(self, periodo: str) -> List[Dict[str, Any]]:
        res = self._request("GET", "canjes", params={"periodo": f"eq.{periodo}", "select": "*"})
        return res if isinstance(res, list) else []
