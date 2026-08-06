import streamlit as st
import pandas as pd

def render_user_selector(df_emp):
    """
    Renderiza el selector de usuario y valida el PIN de 4 dígitos dinámico desde Google Sheets.
    Garantiza que SOLO el Responsable de Operaciones / Producción tenga Acceso Total en Aprobaciones.
    """
    if df_emp is None or df_emp.empty:
        st.sidebar.warning("⚠️ No se pudo cargar el Maestro de Empleados.")
        return None, "Admin", [], False

    # Normalizar nombres de columnas
    cols = {str(c).strip().lower(): c for c in df_emp.columns}
    c_nombre = next((cols[k] for k in cols if 'nombre' in k), df_emp.columns[1])
    c_sup = next((cols[k] for k in cols if 'supervisor' in k), None)
    c_rol = next((cols[k] for k in cols if 'rol' in k), None)
    c_pin = next((cols[k] for k in cols if 'pin' in k), None)

    # 1. Lista de Supervisores únicos
    supervisores = []
    if c_sup and c_sup in df_emp.columns:
        supervisores = [
            str(s).strip() for s in df_emp[c_sup].dropna().unique() 
            if str(s).strip().upper() not in ['N/A', 'NONE', '', 'NAN']
        ]

    # 2. Lista de Jefaturas y Responsables de Operaciones
    jefes_admins = []
    if c_rol and c_rol in df_emp.columns:
        filtro_jefes = df_emp[c_rol].astype(str).str.contains(
            'Operaciones|Produccion|Producción|Gerente|Jefe|Jefatura', case=False, na=False
        )
        jefes_admins = [str(n).strip() for n in df_emp[filtro_jefes][c_nombre].unique() if str(n).strip()]

    lista_usuarios = sorted(list(set(supervisores + jefes_admins)))
    if not lista_usuarios:
        lista_usuarios = sorted([str(n).strip() for n in df_emp[c_nombre].unique() if str(n).strip()])

    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Credenciales de Supervisor")
    usuario_actual = st.sidebar.selectbox("Seleccione su Nombre:", lista_usuarios)

    # Extraer el PIN configurado en Excel/Google Sheets para este usuario
    row_user = df_emp[df_emp[c_nombre].astype(str).str.strip().str.upper() == usuario_actual.strip().upper()]
    
    pin_esperado = "1234" # Valor por defecto de respaldo
    if c_pin and not row_user.empty:
        val_pin = str(row_user[c_pin].values[0]).strip()
        if val_pin and val_pin.lower() != 'nan':
            pin_esperado = val_pin.split('.')[0] # Limpia decimales si vienen formato número

    # Campo para PIN de 4 dígitos
    pin_ingresado = st.sidebar.text_input("Ingrese su PIN (4 dígitos):", type="password", max_chars=4)

    pin_valido = False
    if pin_ingresado == pin_esperado:
        pin_valido = True
        st.sidebar.success("🔑 PIN Correcto")
    elif pin_ingresado != "":
        st.sidebar.error("❌ PIN Incorrecto")

    # Identificar si el usuario tiene Rol de Acceso Total (Ever Medrano / Operaciones y Producción)
    rol_registrado = str(row_user[c_rol].values[0]).upper() if (c_rol and not row_user.empty) else ""
    es_responsable_operaciones = "MEDRANO" in usuario_actual.upper() or any(
        k in rol_registrado for k in ['OPERACIONES', 'PRODUCCION', 'PRODUCCIÓN', 'GERENTE']
    )

    if es_responsable_operaciones:
        rol = "Jefe de Producción"
        empleados_a_cargo = list(df_emp[c_nombre].unique()) # Acceso a todo el personal
        st.sidebar.success("👑 Rol: Responsable de Operaciones y Producción (Acceso Total)")
    else:
        rol = "Supervisor"
        if c_sup:
            df_a_cargo = df_emp[df_emp[c_sup].astype(str).str.strip().str.upper() == usuario_actual.strip().upper()]
            empleados_a_cargo = list(df_a_cargo[c_nombre].unique())
        else:
            empleados_a_cargo = []
        st.sidebar.info(f"📋 Personal Asignado: {len(empleados_a_cargo)} personas")

    return usuario_actual, rol, empleados_a_cargo, pin_valido


def filter_dataframe_by_supervisor(df, columna_nombre, empleados_a_cargo, rol):
    """
    Filtra cualquier DataFrame mostrando únicamente el personal asignado al supervisor.
    Si el usuario es Responsable de Operaciones y Producción, retorna el 100% de la información.
    """
    if df is None or df.empty:
        return df

    if rol == "Jefe de Producción":
        return df

    if columna_nombre in df.columns:
        return df[df[columna_nombre].isin(empleados_a_cargo)]
    
    return df
