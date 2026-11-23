from decimal import Decimal
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from multas.models import Multa
from .models import Prestamo, Reserva

from datetime import timedelta


# Calcula el saldo total pendiente de multas de un usuario (CU-06 excepción 4a)
def saldo_multas_pendientes(usuario):
    multas_pendientes = Multa.objects.filter(usuario=usuario, estado='PENDIENTE')
    total_multas = multas_pendientes.aggregate(
        t=Coalesce(Sum('monto'), Decimal('0.00'))
    )['t']
    total_pagado = multas_pendientes.aggregate(
        t=Coalesce(Sum('pago__monto'), Decimal('0.00'))
    )['t']
    return max(total_multas - total_pagado, Decimal('0.00'))


# Cuenta los préstamos en curso y las reservas con ejemplar ya apartado (RN-02)
def libros_en_uso(usuario, excluir_reserva_id=None):
    prestamos = Prestamo.objects.filter(
        usuario=usuario,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).count()

    reservas_apartadas = Reserva.objects.filter(
        usuario=usuario,
        estado='DISPONIBLE'
    )
    if excluir_reserva_id is not None:
        reservas_apartadas = reservas_apartadas.exclude(id=excluir_reserva_id)

    return prestamos + reservas_apartadas.count()


# Elegibilidad del usuario (CU-07, RN-08).
# Devuelve el motivo si no puede pedir ni renovar libros, o '' si está al corriente.
def motivo_inelegible(usuario):
    if usuario.bloqueado:
        detalle = f" Motivo: {usuario.motivo_bloqueo}." if usuario.motivo_bloqueo else ""
        return f"Tu cuenta está bloqueada.{detalle}"

    if Multa.objects.filter(usuario=usuario, estado='PENDIENTE').exists():
        saldo = saldo_multas_pendientes(usuario)
        return (
            f"Tienes multas pendientes por un saldo de ${saldo:.2f} MXN. "
            "Págalas primero (RN-08)."
        )

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



def liberar_o_asignar_ejemplar(ejemplar, ahora=None):
    """RN-12: al liberarse un ejemplar, lo asigna a la reserva PENDIENTE mas
    antigua del titulo (FIFO) o, si no hay, lo deja DISPONIBLE.

    Debe llamarse dentro de transaction.atomic().
    Devuelve la Reserva asignada o None.
    """
    from cuentas.models import Notificacion
    from .models import PoliticaPrestamo, Reserva

    ahora = ahora or timezone.now()

    reserva = (
        Reserva.objects.select_for_update()
        .select_related('usuario')
        .filter(libro_id=ejemplar.libro_id, estado='PENDIENTE')
        .order_by('fecha_reserva', 'id')
        .first()
    )

    if reserva is None:
        ejemplar.estado = 'DISPONIBLE'
        ejemplar.save()
        return None

    try:
        horas = PoliticaPrestamo.objects.get(
            tipo_usuario=reserva.usuario.tipo_usuario
        ).horas_para_recoger
    except PoliticaPrestamo.DoesNotExist:
        horas = 48  # RN-06 por defecto

    reserva.ejemplar_asignado = ejemplar
    reserva.estado = 'DISPONIBLE'
    reserva.fecha_expiracion = ahora + timedelta(hours=horas)
    reserva.save()

    ejemplar.estado = 'RESERVADO'
    ejemplar.save()

    Notificacion.objects.create(
        usuario=reserva.usuario,
        tipo='RESERVA_DISPONIBLE',
        mensaje=(
            f'Tu reserva de "{ejemplar.libro.titulo}" ya esta disponible. '
            f'Recogela antes del '
            f'{timezone.localtime(reserva.fecha_expiracion):%d/%m/%Y %H:%M}.'
        ),
        leida=0,
        fecha=ahora,
    )
    return reserva