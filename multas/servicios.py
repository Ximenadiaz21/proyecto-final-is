"""Capa de servicios de dominio para cobro y condonación de multas (RNF-06, RNF-03).

Centraliza las reglas de CU-28 (registrar pago) y CU-29 (condonar multa, RN-14)
dentro de transacciones atómicas desacopladas de la capa HTTP.
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from prestamos.servicios import ReglaNegocioError
from .models import Multa, Pago


# CU-28: Registra un pago total o parcial sobre una multa pendiente (RNF-03, RF-12)
@transaction.atomic
def registrar_pago(multa_id, monto_crudo, metodo, bibliotecario):
    if not bibliotecario.es_bibliotecario:
        raise ReglaNegocioError("Solo el bibliotecario puede registrar pagos de multas.")

    if metodo not in Pago.Metodo.values:
        raise ReglaNegocioError("Selecciona un método de pago válido.")

    try:
        monto = Decimal(str(monto_crudo)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        raise ReglaNegocioError("El monto no es válido.")

    multa = Multa.objects.select_for_update().get(id=multa_id)

    if multa.estado != Multa.Estado.PENDIENTE:
        raise ReglaNegocioError("Esta multa ya no está pendiente.")

    saldo = multa.saldo()
    if monto <= Decimal('0.00') or monto > saldo:
        raise ReglaNegocioError(
            f"El monto debe ser mayor a $0.00 y no puede exceder el saldo (${saldo:.2f})."
        )

    ahora = timezone.now()
    num_pago = multa.pago_set.count() + 1
    folio = f"REC-{timezone.localtime(ahora):%Y%m%d%H%M%S}-{multa.id}-{num_pago}"

    pago = Pago.objects.create(
        multa=multa,
        monto=monto,
        metodo=metodo,
        folio_recibo=folio,
        fecha_pago=ahora,
        registrado_por=bibliotecario,
    )

    # Si el pago liquida el saldo restante, la multa pasa a PAGADA
    if monto == saldo:
        multa.estado = Multa.Estado.PAGADA
        multa.save(update_fields=['estado'])

    return pago, multa


# CU-29: Condona una multa pendiente exigiendo rol bibliotecario y justificación (RN-14)
@transaction.atomic
def condonar_multa(multa_id, justificacion, bibliotecario):
    if not bibliotecario.es_bibliotecario:
        raise ReglaNegocioError("Solo el bibliotecario puede condonar multas (RN-14).")

    justificacion = (justificacion or '').strip()
    if not justificacion:
        raise ReglaNegocioError("Debes escribir una justificación para condonar la multa (RN-14).")

    if len(justificacion) > 255:
        raise ReglaNegocioError("La justificación no puede pasar de 255 caracteres.")

    multa = Multa.objects.select_for_update().get(id=multa_id)

    if multa.estado != Multa.Estado.PENDIENTE:
        raise ReglaNegocioError("Esta multa ya no está pendiente.")

    multa.estado = Multa.Estado.CONDONADA
    multa.justificacion_condonacion = justificacion
    multa.condonada_por = bibliotecario
    multa.save(update_fields=['estado', 'justificacion_condonacion', 'condonada_por'])
    return multa
