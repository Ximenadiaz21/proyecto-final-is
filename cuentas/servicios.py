"""Servicio centralizado de notificaciones internas y por correo (RF-15, RNF-03).

Separa el envío de correos del método Model.save() para evitar efectos secundarios
ocultos al cargar datos de prueba o editar registros desde Django Admin.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Notificacion


# Asunto del correo electrónico según el tipo de notificación registrado
ASUNTOS_CORREO = {
    Notificacion.Tipo.VENCE_PRONTO: 'Recordatorio de vencimiento próximo - Biblioteca Escolar',
    Notificacion.Tipo.VENCIDO: 'Aviso de préstamo vencido - Biblioteca Escolar',
    Notificacion.Tipo.RESERVA_DISPONIBLE: 'Tu libro reservado ya está disponible - Biblioteca Escolar',
    Notificacion.Tipo.MULTA: 'Aviso de multa registrada - Biblioteca Escolar',
    Notificacion.Tipo.GENERAL: 'Notificación - Biblioteca Escolar',
}


# Envía el correo electrónico correspondiente a una notificación ya guardada (RF-15, CU-36)
def enviar_correo_notificacion(notificacion):
    # Si el usuario no tiene correo registrado, se omite el envío sin error
    if not notificacion.usuario_id or not notificacion.usuario.email:
        return

    asunto = ASUNTOS_CORREO.get(notificacion.tipo, 'Notificación - Biblioteca Escolar')
    nombre = notificacion.usuario.get_full_name() or notificacion.usuario.username
    cuerpo = (
        f"Hola {nombre},\n\n"
        f"{notificacion.mensaje}\n\n"
        f"Puedes consultar tus préstamos, reservas y notificaciones iniciando sesión "
        f"en el Sistema de Gestión de Biblioteca Escolar.\n\n"
        f"Atentamente,\n"
        f"Biblioteca Escolar"
    )

    # fail_silently=True evita que un problema de red interrumpa la operación principal
    send_mail(
        subject=asunto,
        message=cuerpo,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@biblioteca.escolar.mx'),
        recipient_list=[notificacion.usuario.email],
        fail_silently=True,
    )


# Crea una notificación en BD y agenda el envío del correo al confirmar la transacción
def notificar(usuario, tipo, mensaje, fecha=None, enviar_email=True):
    # Trunca a 500 caracteres para respetar la longitud máxima de la columna mensaje
    notificacion = Notificacion.objects.create(
        usuario=usuario,
        tipo=tipo,
        mensaje=mensaje[:500],
        leida=False,
        fecha=fecha or timezone.now(),
    )
    # on_commit garantiza que el correo solo salga si la transacción terminó sin revertirse
    if enviar_email:
        transaction.on_commit(lambda: enviar_correo_notificacion(notificacion))
    return notificacion
