from .models import Notificacion


# Inyecta el conteo de notificaciones no leídas en todas las plantillas autenticadas
def notificaciones_context(request):
    usuario = getattr(request, 'user', None)
    if usuario and usuario.is_authenticated:
        no_leidas = Notificacion.objects.filter(usuario=usuario, leida=False).count()
        return {'notificaciones_no_leidas': no_leidas}
    return {'notificaciones_no_leidas': 0}
