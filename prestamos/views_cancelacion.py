from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from cuentas.permisos import lector_requerido
from . import servicios
from .models import Prestamo
from .servicios import ReglaNegocioError


# El lector cancela una solicitud que todavía no recogió (CU-08)
@lector_requerido
@require_POST
def cancelar_solicitud(request, prestamo_id):
    try:
        servicios.cancelar_solicitud(prestamo_id, request.user)
    except Prestamo.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('mis_prestamos')

    messages.success(request, "Solicitud cancelada. El ejemplar quedó disponible de nuevo.")
    return redirect('mis_prestamos')
