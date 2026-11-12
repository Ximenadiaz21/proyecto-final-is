from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Ejemplar
from .models import Prestamo
from .reglas import liberar_o_asignar_ejemplar


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

        # Libera el ejemplar o lo asigna al siguiente usuario en la cola de reservas (RN-12)
        ejemplar = Ejemplar.objects.select_for_update().select_related('libro').get(pk=prestamo.ejemplar_id)
        if ejemplar.estado == 'RESERVADO':
            liberar_o_asignar_ejemplar(ejemplar, timezone.now())

    messages.success(request, "Solicitud cancelada. El ejemplar quedó disponible de nuevo.")
    return redirect('mis_prestamos')
