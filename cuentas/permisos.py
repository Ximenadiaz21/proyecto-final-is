"""Control de acceso por rol para las vistas del sistema (RF-01, RNF-01).

Todos los decoradores verifican primero la sesión con @login_required y,
si el rol del usuario no corresponde, responden con HTTP 403 (PermissionDenied).
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


# Verifica que el usuario sea un bibliotecario autenticado y sin bloqueo administrativo
def es_bibliotecario(usuario):
    return (
        usuario.is_authenticated
        and usuario.tipo_usuario == 'BIBLIOTECARIO'
        and not usuario.bloqueado
    )


# Verifica que el usuario pertenezca a un rol lector (estudiante o profesor)
def es_lector(usuario):
    return (
        usuario.is_authenticated
        and usuario.tipo_usuario in ('ESTUDIANTE', 'PROFESOR')
    )


# Verifica que el usuario tenga el rol de profesor
def es_profesor(usuario):
    return (
        usuario.is_authenticated
        and usuario.tipo_usuario == 'PROFESOR'
    )


# Restringe una vista únicamente a bibliotecarios activos (lanza 403 si no cumple)
def bibliotecario_requerido(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_bibliotecario(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    # login_required envuelve la función para redirigir al login si no hay sesión
    return login_required(envoltura)


# Restringe una vista únicamente a estudiantes y profesores (lanza 403 a otros roles)
def lector_requerido(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_lector(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return login_required(envoltura)


# Restringe una vista únicamente a profesores (ej. sugerencias de adquisición CU-16)
def profesor_requerido(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_profesor(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return login_required(envoltura)
