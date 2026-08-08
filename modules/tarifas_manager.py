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


def cargar_tarifas() -> Dict[str, Any]:
    """Carga las tarifas locales. Si el archivo no existe, crea la estructura inicial."""
    if not os.path.exists(CONFIG_TARIFAS_PATH):
        guardar_tarifas(DEFAULT_TARIFAS)
        return DEFAULT_TARIFAS

    try:
        with open(CONFIG_TARIFAS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error al cargar config_tarifas.json: {e}")
        return DEFAULT_TARIFAS


def guardar_tarifas(data: Dict[str, Any]) -> bool:
    """Guarda la configuración de tarifas y excepciones en JSON local."""
    try:
        with open(CONFIG_TARIFAS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error al guardar config_tarifas.json: {e}")
        return False


def obtener_config_periodo(periodo: str) -> Dict[str, Any]:
    """Obtiene la configuración específica para un período (ej: '2026-07'). Si no existe, retorna los valores por defecto."""
    config_global = cargar_tarifas()
    periodos = config_global.get("periodos", {})
    if periodo in periodos:
        return periodos[periodo]
    return {
        "tarifas_base": config_global.get("tarifas_base", DEFAULT_TARIFAS["tarifas_base"]),
        "excepciones": {}
    }


def guardar_config_periodo(periodo: str, config_periodo: Dict[str, Any]) -> bool:
    """Guarda la configuración específica de un período en el JSON global."""
    config_global = cargar_tarifas()
    if "periodos" not in config_global:
        config_global["periodos"] = {}
    config_global["periodos"][periodo] = config_periodo
    return guardar_tarifas(config_global)


def obtener_tarifa_empleado(ci: str, tipo_turno: str, periodo: str = "") -> float:
    """Obtiene la tarifa para un jornalero (revisa si tiene excepción por CI o usa la base del período)."""
    if periodo:
        cfg = obtener_config_periodo(periodo)
    else:
        cfg = cargar_tarifas()

    ci_str = str(ci).strip()
    if ci_str in cfg.get("excepciones", {}):
        exc = cfg["excepciones"][ci_str]
        if tipo_turno in exc and exc[tipo_turno] is not None:
            return float(exc[tipo_turno])

    return float(cfg.get("tarifas_base", {}).get(tipo_turno, 0.0))


def actualizar_excepcion_empleado(ci: str, tipo_turno: str, monto: float, periodo: str = ""):
    """Agrega o actualiza una tarifa excepcionada para un CI específico en un período."""
    if periodo:
        cfg = obtener_config_periodo(periodo)
        if "excepciones" not in cfg:
            cfg["excepciones"] = {}
        ci_str = str(ci).strip()
        if ci_str not in cfg["excepciones"]:
            cfg["excepciones"][ci_str] = {}
        cfg["excepciones"][ci_str][tipo_turno] = float(monto)
        guardar_config_periodo(periodo, cfg)
    else:
        config = cargar_tarifas()
        ci_str = str(ci).strip()
        if "excepciones" not in config:
            config["excepciones"] = {}
        if ci_str not in config["excepciones"]:
            config["excepciones"][ci_str] = {}
        config["excepciones"][ci_str][tipo_turno] = float(monto)
        guardar_tarifas(config)


def eliminar_excepcion_empleado(ci: str, periodo: str = ""):
    """Elimina las excepciones de un empleado por su CI en un período determinado."""
    if periodo:
        cfg = obtener_config_periodo(periodo)
        ci_str = str(ci).strip()
        if "excepciones" in cfg and ci_str in cfg["excepciones"]:
            del cfg["excepciones"][ci_str]
            guardar_config_periodo(periodo, cfg)
    else:
        config = cargar_tarifas()
        ci_str = str(ci).strip()
        if "excepciones" in config and ci_str in config["excepciones"]:
            del config["excepciones"][ci_str]
            guardar_tarifas(config)
