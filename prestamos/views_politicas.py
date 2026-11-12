from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cuentas.views_usuarios import bibliotecario_requerido
from .models import PoliticaPrestamo


# Valores predeterminados según las reglas de negocio RN-01 a RN-06
VALORES_INICIALES = {
    'ESTUDIANTE': {
        'dias_prestamo': 7,
        'max_libros': 3,
        'max_renovaciones': 1,
        'multa_por_dia': Decimal('10.00'),
        'multa_maxima': Decimal('300.00'),
        'horas_para_recoger': 48,
    },
    'PROFESOR': {
        'dias_prestamo': 30,
        'max_libros': 10,
        'max_renovaciones': 2,
        'multa_por_dia': Decimal('10.00'),
        'multa_maxima': Decimal('300.00'),
        'horas_para_recoger': 48,
    },
}


# Garantiza que existan los registros de política para estudiante y profesor
def _asegurar_politicas():
    ahora = timezone.now()
    for tipo, valores in VALORES_INICIALES.items():
        PoliticaPrestamo.objects.get_or_create(
            tipo_usuario=tipo,
            defaults={**valores, 'actualizado_en': ahora},
        )


# Convierte un valor de texto a entero dentro de un rango permitido
def _leer_entero(valor_texto, nombre_campo, minimo, maximo=365):
    try:
        numero = int(valor_texto)
    except (TypeError, ValueError):
        return None, f"El campo «{nombre_campo}» debe ser un número entero."

    if numero < minimo or numero > maximo:
        return None, f"El campo «{nombre_campo}» debe estar entre {minimo} y {maximo}."

    return numero, ''


# Convierte un valor de texto a decimal monetario válido
def _leer_decimal(valor_texto, nombre_campo):
    try:
        monto = Decimal(valor_texto).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return None, f"El campo «{nombre_campo}» debe ser un monto válido."

    if monto < Decimal('0.00') or monto > Decimal('999999.99'):
        return None, f"El campo «{nombre_campo}» debe ser mayor o igual a $0.00."

    return monto, ''


# Permite al bibliotecario consultar y modificar las políticas de préstamo (CU-31, RF-13)
@bibliotecario_requerido
def configurar_politicas(request):
    # Asegura que existan las dos políticas base en la base de datos
    _asegurar_politicas()

    # Si el bibliotecario envía cambios por POST, valida y actualiza la política indicada
    if request.method == 'POST':
        tipo = request.POST.get('tipo_usuario', '').strip()

        if tipo not in ('ESTUDIANTE', 'PROFESOR'):
            messages.error(request, "Tipo de usuario no válido para configurar la política.")
            return redirect('configurar_politicas')

        # 1. Valida cada parámetro numérico de las reglas RN-01 a RN-06
        dias_prestamo, err1 = _leer_entero(
            request.POST.get('dias_prestamo'), 'Días de préstamo (RN-01)', 1, 365
        )
        max_libros, err2 = _leer_entero(
            request.POST.get('max_libros'), 'Máximo de libros simultáneos (RN-02)', 1, 50
        )
        max_renovaciones, err3 = _leer_entero(
            request.POST.get('max_renovaciones'), 'Renovaciones permitidas (RN-03)', 0, 20
        )
        multa_por_dia, err4 = _leer_decimal(
            request.POST.get('multa_por_dia'), 'Multa por día de retraso (RN-04)'
        )
        multa_maxima, err5 = _leer_decimal(
            request.POST.get('multa_maxima'), 'Multa máxima por préstamo (RN-05)'
        )
        horas_para_recoger, err6 = _leer_entero(
            request.POST.get('horas_para_recoger'), 'Horas para recoger libro apartado (RN-06)', 1, 720
        )

        errores = [e for e in (err1, err2, err3, err4, err5, err6) if e]

        # Verifica que la multa máxima no sea menor que la multa de un solo día
        if not errores and multa_maxima < multa_por_dia:
            errores.append(
                "La multa máxima por préstamo (RN-05) no puede ser menor que la multa por día (RN-04)."
            )

        if errores:
            for error in errores:
                messages.error(request, error)
            return redirect('configurar_politicas')

        # 2. Guarda los cambios dentro de una transacción atómica
        with transaction.atomic():
            politica = get_object_or_404(
                PoliticaPrestamo.objects.select_for_update(),
                tipo_usuario=tipo
            )
            politica.dias_prestamo = dias_prestamo
            politica.max_libros = max_libros
            politica.max_renovaciones = max_renovaciones
            politica.multa_por_dia = multa_por_dia
            politica.multa_maxima = multa_maxima
            politica.horas_para_recoger = horas_para_recoger
            politica.actualizado_en = timezone.now()
            politica.save()

        messages.success(
            request,
            f"Política de préstamo para {politica.get_tipo_usuario_display()} actualizada correctamente."
        )
        return redirect('configurar_politicas')

    # Obtiene las políticas actuales ordenadas (Estudiante primero, Profesor después)
    politica_estudiante = PoliticaPrestamo.objects.get(tipo_usuario='ESTUDIANTE')
    politica_profesor = PoliticaPrestamo.objects.get(tipo_usuario='PROFESOR')

    contexto = {
        'usuario': request.user,
        'titulo': 'Políticas de préstamo',
        'politicas': [politica_estudiante, politica_profesor],
    }

    return render(request, 'prestamos/configurar_politicas.html', contexto)
