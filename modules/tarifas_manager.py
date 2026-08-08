import json
import os
from typing import Dict, Any, List

CONFIG_TARIFAS_PATH = "config_tarifas.json"

DEFAULT_TARIFAS = {
    "tarifas_base": {
        "diurno_normal": 100.0,
        "diurno_1_5": 150.0,
        "nocturno_normal": 120.0,
        "nocturno_1_5": 180.0
    },
    "excepciones": {}
}


def clean_ci(ci_val: Any) -> str:
    """Limpia el Carnet de Identidad eliminando '.0' y espacios redundantes."""
    if ci_val is None:
        return ""
    s = str(ci_val).strip()
    if s.lower() in ("nan", "none", "null"):
        return ""
    if s.endswith(".0"):
        return s[:-2].strip()
    try:
        if "." in s:
            f = float(s)
            if f.is_integer():
                return str(int(f)).strip()
    except (ValueError, TypeError):
        pass
    return s


def _normalize_excepciones_dict(excepciones: Dict[str, Any]) -> Dict[str, Any]:
    """Asegura que todas las llaves de CI en el diccionario de excepciones estén limpias."""
    if not isinstance(excepciones, dict):
        return {}
    norm = {}
    for k, v in excepciones.items():
        norm[clean_ci(k)] = v
    return norm


def cargar_tarifas() -> Dict[str, Any]:
    """Carga las tarifas locales. Si el archivo no existe, crea la estructura inicial."""
    if not os.path.exists(CONFIG_TARIFAS_PATH):
        guardar_tarifas(DEFAULT_TARIFAS)
        return DEFAULT_TARIFAS

    try:
        with open(CONFIG_TARIFAS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "excepciones" in data:
                data["excepciones"] = _normalize_excepciones_dict(data["excepciones"])
            return data
    except Exception as e:
        print(f"Error al cargar config_tarifas.json: {e}")
        return DEFAULT_TARIFAS


def guardar_tarifas(data: Dict[str, Any]) -> bool:
    """Guarda la configuración de tarifas y excepciones en JSON local."""
    try:
        if "excepciones" in data:
            data["excepciones"] = _normalize_excepciones_dict(data["excepciones"])
        with open(CONFIG_TARIFAS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error al guardar config_tarifas.json: {e}")
        return False


def obtener_config_periodo(periodo: str) -> Dict[str, Any]:
    """Obtiene la configuración específica para un período. Si no existe, retorna los valores por defecto."""
    config_global = cargar_tarifas()
    periodos = config_global.get("periodos", {})
    if periodo in periodos:
        cfg = periodos[periodo]
        if "excepciones" in cfg:
            cfg["excepciones"] = _normalize_excepciones_dict(cfg["excepciones"])
        return cfg
    return {
        "tarifas_base": config_global.get("tarifas_base", DEFAULT_TARIFAS["tarifas_base"]),
        "excepciones": {}
    }


def guardar_config_periodo(periodo: str, config_periodo: Dict[str, Any]) -> bool:
    """Guarda la configuración específica de un período en el JSON global."""
    config_global = cargar_tarifas()
    if "periodos" not in config_global:
        config_global["periodos"] = {}

    if "excepciones" in config_periodo:
        config_periodo["excepciones"] = _normalize_excepciones_dict(config_periodo["excepciones"])

    config_global["periodos"][periodo] = config_periodo
    return guardar_tarifas(config_global)


def obtener_tarifa_empleado(ci: str, tipo_turno: str, periodo: str = "") -> float:
    """Obtiene la tarifa para un jornalero (revisa si tiene excepción por CI limpio o usa la base del período)."""
    if periodo:
        cfg = obtener_config_periodo(periodo)
    else:
        cfg = cargar_tarifas()

    ci_str = clean_ci(ci)
    excepciones = _normalize_excepciones_dict(cfg.get("excepciones", {}))

    if ci_str in excepciones:
        exc = excepciones[ci_str]
        if tipo_turno in exc and exc[tipo_turno] is not None:
            return float(exc[tipo_turno])

    return float(cfg.get("tarifas_base", {}).get(tipo_turno, 0.0))


def actualizar_excepcion_empleado(ci: str, tipo_turno: str, monto: float, periodo: str = ""):
    """Agrega o actualiza una tarifa excepcionada para un CI específico en un período."""
    ci_str = clean_ci(ci)
    if not ci_str:
        return

    if periodo:
        cfg = obtener_config_periodo(periodo)
        if "excepciones" not in cfg:
            cfg["excepciones"] = {}
        cfg["excepciones"] = _normalize_excepciones_dict(cfg["excepciones"])

        if ci_str not in cfg["excepciones"]:
            cfg["excepciones"][ci_str] = {}
        cfg["excepciones"][ci_str][tipo_turno] = float(monto)
        guardar_config_periodo(periodo, cfg)
    else:
        config = cargar_tarifas()
        if "excepciones" not in config:
            config["excepciones"] = {}
        config["excepciones"] = _normalize_excepciones_dict(config["excepciones"])

        if ci_str not in config["excepciones"]:
            config["excepciones"][ci_str] = {}
        config["excepciones"][ci_str][tipo_turno] = float(monto)
        guardar_tarifas(config)


def eliminar_excepcion_empleado(ci: str, periodo: str = ""):
    """Elimina las excepciones de un empleado por su CI en un período determinado."""
    ci_str = clean_ci(ci)
    if not ci_str:
        return

    if periodo:
        cfg = obtener_config_periodo(periodo)
        excepciones = _normalize_excepciones_dict(cfg.get("excepciones", {}))
        if ci_str in excepciones:
            del excepciones[ci_str]
            cfg["excepciones"] = excepciones
            guardar_config_periodo(periodo, cfg)
    else:
        config = cargar_tarifas()
        excepciones = _normalize_excepciones_dict(config.get("excepciones", {}))
        if ci_str in excepciones:
            del excepciones[ci_str]
            config["excepciones"] = excepciones
            guardar_tarifas(config)
