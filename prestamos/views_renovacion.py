from datetime import timedelta

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cuentas.permisos import lector_requerido
from . import servicios
from .models import PoliticaPrestamo, Prestamo
from .reglas import motivo_no_renovable
from .servicios import ReglaNegocioError


# Renueva un préstamo activo (CU-10).
# GET muestra la nueva fecha para confirmar; POST aplica la renovación vía capa de servicios.
@lector_requerido
def renovar_prestamo(request, prestamo_id):
    usuario = request.user

    # Si confirma por POST, aplica la renovación de forma atómica en la capa de servicios
    if request.method == 'POST':
        try:
            _, nueva_fecha = servicios.renovar_prestamo(prestamo_id, usuario)
        except Prestamo.DoesNotExist:
            raise Http404
        except ReglaNegocioError as error:
            messages.error(request, str(error))
            return redirect('mis_prestamos')

        messages.success(
            request,
            f"Préstamo renovado. Nueva fecha de devolución: {nueva_fecha:%d/%m/%Y}.",
        )
        return redirect('mis_prestamos')

    # En GET verifica reglas y muestra la pantalla de confirmación con la nueva fecha estimada
    prestamo = get_object_or_404(Prestamo, id=prestamo_id, usuario=usuario)
    try:
        politica = PoliticaPrestamo.objects.get(tipo_usuario=usuario.tipo_usuario)
    except PoliticaPrestamo.DoesNotExist:
        messages.error(request, "No hay una política de préstamo configurada para tu tipo de usuario.")
        return redirect('mis_prestamos')

    motivo = motivo_no_renovable(prestamo, politica)
    if motivo:
        messages.error(request, motivo)
        return redirect('mis_prestamos')

    nueva_fecha = timezone.localdate() + timedelta(days=politica.dias_prestamo)
    contexto = {
        'usuario': usuario,
        'titulo': 'Renovar préstamo',
        'prestamo': prestamo,
        'politica': politica,
        'nueva_fecha': nueva_fecha,
        'restantes': politica.max_renovaciones - prestamo.num_renovaciones,
    }
    return render(request, 'prestamos/confirmar_renovacion.html', contexto)
