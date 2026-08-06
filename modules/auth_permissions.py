import streamlit as st
import pandas as pd

def render_user_selector(df_emp):
    """
    Renderiza el selector de usuario en la barra lateral basándose únicamente
    en nombres reales registrados en el Maestro de Empleados.
    """
    if df_emp is None or df_emp.empty:
        st.sidebar.warning("⚠️ No se pudo cargar el Maestro de Empleados.")
        return None, "Admin", []

    # Normalizar nombres de columnas
    cols = {str(c).strip().lower(): c for c in df_emp.columns}
    c_nombre = next((cols[k] for k in cols if 'nombre' in k), df_emp.columns[1])
    c_sup = next((cols[k] for k in cols if 'supervisor' in k), None)
    c_rol = next((cols[k] for k in cols if 'rol' in k), None)

    # 1. Lista de Supervisores únicos
    supervisores = []
    if c_sup and c_sup in df_emp.columns:
        supervisores = [
            str(s).strip() for s in df_emp[c_sup].dropna().unique() 
            if str(s).strip().upper() not in ['N/A', 'NONE', '', 'NAN']
        ]

    # 2. Lista de Jefaturas / Responsables según columna Rol
    jefes_admins = []
    if c_rol and c_rol in df_emp.columns:
        filtro_jefes = df_emp[c_rol].astype(str).str.contains(
            'Jefe|Admin|Responsable|Operaciones|Gerente|Jefatura', case=False, na=False
        )
        jefes_admins = [str(n).strip() for n in df_emp[filtro_jefes][c_nombre].unique() if str(n).strip()]

    # 3. Lista unificada SOLO con nombres reales (sin etiquetas genéricas)
    lista_usuarios = sorted(list(set(supervisores + jefes_admins)))

    if not lista_usuarios:
        lista_usuarios = sorted([str(n).strip() for n in df_emp[c_nombre].unique() if str(n).strip()])

    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Sesión de Usuario")
    usuario_actual = st.sidebar.selectbox("Seleccione su Usuario:", lista_usuarios)

    # Validar si el usuario seleccionado es el Responsable / Jefe (Acceso Total)
    es_jefe = False
    if c_rol and c_rol in df_emp.columns:
        m_emp = df_emp[df_emp[c_nombre].astype(str).str.strip().str.upper() == usuario_actual.strip().upper()]
        if not m_emp.empty:
            rol_registrado = str(m_emp[c_rol].values[0]).lower()
            if any(k in rol_registrado for k in ['jefe', 'admin', 'responsable', 'operaciones', 'gerente']):
                es_jefe = True

    # Regla para tu usuario o cualquier perfil con rol de Jefatura/Operaciones
    if es_jefe or usuario_actual in jefes_admins or "MEDRANO" in usuario_actual.upper():
        rol = "Jefe de Producción"
        empleados_a_cargo = list(df_emp[c_nombre].unique())  # Acceso Total
        st.sidebar.success("👑 Rol: Responsable de Operaciones y Producción (Acceso Total)")
    else:
        rol = "Supervisor"
        if c_sup:
            df_a_cargo = df_emp[df_emp[c_sup].astype(str).str.strip().str.upper() == usuario_actual.strip().upper()]
            empleados_a_cargo = list(df_a_cargo[c_nombre].unique())
        else:
            empleados_a_cargo = []
        
        st.sidebar.info(f"📋 Rol: Supervisor ({len(empleados_a_cargo)} a cargo)")

    return usuario_actual, rol, empleados_a_cargo


def filter_dataframe_by_supervisor(df, columna_nombre, empleados_a_cargo, rol):
    """
    Filtra cualquier DataFrame para mostrar solo los empleados asignados.
    Si el rol es 'Jefe de Producción' (Acceso Total), muestra el 100% de los datos.
    """
    if df is None or df.empty:
        return df

    # El Responsable de Operaciones / Jefe ve todo el sistema
    if rol == "Jefe de Producción":
        return df

    if columna_nombre in df.columns:
        return df[df[columna_nombre].isin(empleados_a_cargo)]
    
    return df
