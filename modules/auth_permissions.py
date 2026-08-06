import streamlit as st
import pandas as pd

def render_user_selector(df_emp):
    """
    Renderiza el selector de usuario en la barra lateral (Sidebar)
    y retorna el usuario actual, su rol y su lista de supervisados.
    """
    if df_emp is None or df_emp.empty:
        st.sidebar.warning("⚠️ No se pudo cargar el Maestro de Empleados.")
        return None, "Admin", []

    # Normalizar columnas
    cols = {str(c).strip().lower(): c for c in df_emp.columns}
    c_nombre = next((cols[k] for k in cols if 'nombre' in k), df_emp.columns[1])
    c_sup = next((cols[k] for k in cols if 'supervisor' in k), None)
    c_rol = next((cols[k] for k in cols if 'rol' in k), None)

    # Identificar lista de usuarios únicos (Supervisores + Admins/Jefes)
    supervisores = []
    if c_sup and c_sup in df_emp.columns:
        supervisores = list(df_emp[c_sup].dropna().unique())

    # Agregar roles especiales si existen
    admins = []
    if c_rol and c_rol in df_emp.columns:
        admins = list(df_emp[df_emp[c_rol].str.contains('Jefe|Admin', case=False, na=False)][c_nombre].unique())

    # Lista total de usuarios para el selector
    usuarios_sistema = sorted(list(set(supervisores + admins + ["Jefe de Producción (Acceso Total)"])))

    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Sesión de Usuario")
    usuario_actual = st.sidebar.selectbox("Seleccione su Usuario:", usuarios_sistema)

    # Determinar Rol y Permisos
    if "Jefe" in usuario_actual or "Admin" in usuario_actual:
        rol = "Jefe de Producción"
        empleados_a_cargo = list(df_emp[c_nombre].unique()) # Acceso total
        st.sidebar.success("👑 Rol: Jefe de Producción (Acceso Total)")
    else:
        rol = "Supervisor"
        # Filtrar solo personal asignado a este supervisor
        if c_sup:
            df_a_cargo = df_emp[df_emp[c_sup].astype(str).str.strip().str.upper() == usuario_actual.strip().upper()]
            empleados_a_cargo = list(df_a_cargo[c_nombre].unique())
        else:
            empleados_a_cargo = []
        
        st.sidebar.info(f"📋 Rol: Supervisor ({len(empleados_a_cargo)} a cargo)")

    return usuario_actual, rol, empleados_a_cargo


def filter_dataframe_by_supervisor(df, columna_nombre, empleados_a_cargo, rol):
    """
    Filtra cualquier DataFrame para mostrar solo los empleados permitidos.
    """
    if df is None or df.empty:
        return df

    # El Jefe de Producción ve todo
    if rol == "Jefe de Producción":
        return df

    if columna_nombre in df.columns:
        return df[df[columna_nombre].isin(empleados_a_cargo)]
    
    return df
