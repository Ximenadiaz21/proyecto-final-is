from django.db.models import Q
from django.utils import timezone

from multas.models import Multa
from .models import Prestamo, Reserva


# Elegibilidad del usuario (CU-07, RN-08).
# Devuelve el motivo si no puede pedir ni renovar libros, o '' si está al corriente.
def motivo_inelegible(usuario):
    if usuario.bloqueado:
        return "Tu cuenta está bloqueada."

    if Multa.objects.filter(usuario=usuario, estado='PENDIENTE').exists():
        return "Tienes multas pendientes. Págalas primero (RN-08)."

    hoy = timezone.localdate()
    vencidos = Prestamo.objects.filter(usuario=usuario).filter(
        Q(estado='VENCIDO') | Q(estado='ACTIVO', fecha_vencimiento__lt=hoy)
    )
    if vencidos.exists():
        return "Tienes préstamos vencidos. Devuélvelos primero (RN-08)."

    return ''


# Reglas para renovar un préstamo (RN-03, RN-08, RN-09).
# Devuelve el motivo del rechazo, o '' si se puede renovar.
def motivo_no_renovable(prestamo, politica):
    hoy = timezone.localdate()

    if prestamo.estado == 'VENCIDO':
        return "El préstamo está vencido; no se puede renovar. Devuélvelo en la biblioteca (RN-09)."

    if prestamo.estado != 'ACTIVO':
        return "Solo se pueden renovar préstamos activos."

    if prestamo.fecha_vencimiento is None or prestamo.fecha_vencimiento < hoy:
        return "El préstamo está vencido; no se puede renovar. Devuélvelo en la biblioteca (RN-09)."

    motivo = motivo_inelegible(prestamo.usuario)
    if motivo:
        return motivo

    if prestamo.num_renovaciones >= politica.max_renovaciones:
        return f"Ya alcanzaste el máximo de renovaciones permitidas ({politica.max_renovaciones}) (RN-03)."

    # Si otro usuario reservó el título, no se puede renovar (RN-09)
    libro_id = prestamo.ejemplar.libro_id
    reservado = Reserva.objects.filter(
        libro_id=libro_id, estado__in=['PENDIENTE', 'DISPONIBLE']
    ).exclude(usuario=prestamo.usuario).exists()

    if reservado:
        return "Otro usuario reservó este título, por lo que no se puede renovar (RN-09)."

    return ''
