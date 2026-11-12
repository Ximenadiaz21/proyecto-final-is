from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from catalogo.models import Ejemplar
from .models import Prestamo


# El lector cancela una solicitud que todavía no recogió (CU-08)
@login_required
@require_POST
def cancelar_solicitud(request, prestamo_id):
    with transaction.atomic():
        # Solo puede cancelar sus propias solicitudes
        prestamo = get_object_or_404(
            Prestamo.objects.select_for_update(),
            id=prestamo_id, usuario=request.user
        )

        if prestamo.estado != 'SOLICITADO':
            messages.error(request, "Solo se pueden cancelar solicitudes que aún no se han recogido.")
            return redirect('mis_prestamos')

        prestamo.estado = 'CANCELADO'
        prestamo.save(update_fields=['estado'])

        # Libera el ejemplar que estaba apartado
        ejemplar = Ejemplar.objects.select_for_update().get(pk=prestamo.ejemplar_id)
        if ejemplar.estado == 'RESERVADO':
            ejemplar.estado = 'DISPONIBLE'
            ejemplar.save(update_fields=['estado'])

    messages.success(request, "Solicitud cancelada. El ejemplar quedó disponible de nuevo.")
    return redirect('mis_prestamos')
