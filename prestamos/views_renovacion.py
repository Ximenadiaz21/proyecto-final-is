from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import PoliticaPrestamo, Prestamo
from .reglas import motivo_no_renovable


# Renueva un préstamo activo (CU-10).
# GET muestra la nueva fecha para confirmar; POST aplica la renovación.
@login_required
def renovar_prestamo(request, prestamo_id):
    usuario = request.user

    if usuario.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Solo estudiantes y profesores pueden renovar préstamos.")
        return redirect('panel')

    with transaction.atomic():
        consulta = Prestamo.objects.select_for_update() if request.method == 'POST' else Prestamo.objects

        # Solo se puede renovar un préstamo propio
        prestamo = get_object_or_404(consulta, id=prestamo_id, usuario=usuario)

        try:
            politica = PoliticaPrestamo.objects.get(tipo_usuario=usuario.tipo_usuario)
        except PoliticaPrestamo.DoesNotExist:
            messages.error(request, "No hay una política de préstamo configurada para tu tipo de usuario.")
            return redirect('mis_prestamos')

        motivo = motivo_no_renovable(prestamo, politica)
        if motivo:
            messages.error(request, motivo)
            return redirect('mis_prestamos')

        # RN-10: la nueva fecha se cuenta desde el día de la renovación
        nueva_fecha = timezone.localdate() + timedelta(days=politica.dias_prestamo)

        if request.method == 'POST':
            prestamo.num_renovaciones += 1
            prestamo.fecha_vencimiento = nueva_fecha
            prestamo.save(update_fields=['num_renovaciones', 'fecha_vencimiento'])

            messages.success(
                request,
                f"Préstamo renovado. Nueva fecha de devolución: {nueva_fecha.strftime('%d/%m/%Y')}."
            )
            return redirect('mis_prestamos')

    contexto = {
        'usuario': usuario,
        'titulo': 'Renovar préstamo',
        'prestamo': prestamo,
        'politica': politica,
        'nueva_fecha': nueva_fecha,
        'restantes': politica.max_renovaciones - prestamo.num_renovaciones,
    }

    return render(request, 'prestamos/confirmar_renovacion.html', contexto)
