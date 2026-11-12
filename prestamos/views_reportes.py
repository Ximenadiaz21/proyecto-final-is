from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from catalogo.models import Libro
from cuentas.views_usuarios import bibliotecario_requerido
from multas.models import Multa, Pago
from multas.views import con_saldos
from .models import Prestamo


# Convierte una cadena YYYY-MM-DD a objeto date; devuelve None si no es válida
def _parsear_fecha(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


# Genera los 4 reportes operativos requeridos por la biblioteca (CU-32, RF-14)
@bibliotecario_requerido
def reportes(request):
    hoy = timezone.localdate()

    # 1. Obtiene el rango de fechas para el reporte de préstamos por periodo
    # Por defecto muestra los últimos 30 días naturales
    inicio_str = request.GET.get('fecha_inicio', '').strip()
    fin_str = request.GET.get('fecha_fin', '').strip()

    fecha_inicio = _parsear_fecha(inicio_str) or (hoy - timedelta(days=30))
    fecha_fin = _parsear_fecha(fin_str) or hoy

    # Si el usuario invirtió el orden de las fechas, las intercambia
    if fecha_inicio > fecha_fin:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio

    # =========================================================================
    # REPORTE 1: Préstamos por periodo (RF-14)
    # =========================================================================
    prestamos_periodo = Prestamo.objects.filter(
        fecha_solicitud__date__gte=fecha_inicio,
        fecha_solicitud__date__lte=fecha_fin,
    ).select_related(
        'usuario', 'ejemplar', 'ejemplar__libro'
    ).order_by('-fecha_solicitud', '-id')

    conteo_estados = {
        fila['estado']: fila['total']
        for fila in prestamos_periodo.values('estado').annotate(total=Count('id'))
    }
    resumen_periodo = [
        (codigo, etiqueta, conteo_estados.get(codigo, 0))
        for codigo, etiqueta in Prestamo.ESTADOS
    ]

    conteo_roles = {
        fila['usuario__tipo_usuario']: fila['total']
        for fila in prestamos_periodo.values('usuario__tipo_usuario').annotate(total=Count('id'))
    }

    # =========================================================================
    # REPORTE 2: Libros más solicitados (RF-14)
    # =========================================================================
    libros_mas_solicitados = Libro.objects.select_related(
        'editorial', 'categoria'
    ).annotate(
        total_prestamos=Count('ejemplar__prestamo', distinct=True),
        total_reservas=Count('reserva', distinct=True),
    ).filter(
        Q(total_prestamos__gt=0) | Q(total_reservas__gt=0)
    ).order_by('-total_prestamos', '-total_reservas', 'titulo')[:10]

    # =========================================================================
    # REPORTE 3: Préstamos vencidos (RF-14)
    # =========================================================================
    prestamos_vencidos_qs = Prestamo.objects.filter(
        Q(estado='VENCIDO') | Q(estado='ACTIVO', fecha_vencimiento__lt=hoy)
    ).select_related(
        'usuario', 'ejemplar', 'ejemplar__libro'
    ).order_by('fecha_vencimiento', 'id')

    prestamos_vencidos = list(prestamos_vencidos_qs)
    for p in prestamos_vencidos:
        p.retraso_actual = p.dias_retraso(hoy)

    # =========================================================================
    # REPORTE 4: Multas cobradas y pendientes (RF-14)
    # =========================================================================
    multas_todas = con_saldos(
        Multa.objects.select_related(
            'usuario', 'prestamo__ejemplar__libro'
        ).order_by('-fecha_generacion', '-id')
    )

    multas_pendientes = [m for m in multas_todas if m.estado == 'PENDIENTE']
    multas_pagadas = [m for m in multas_todas if m.estado == 'PAGADA']
    multas_condonadas = [m for m in multas_todas if m.estado == 'CONDONADA']

    # Total efectivamente cobrado en caja (incluyendo pagos totales y parciales)
    total_cobrado = Pago.objects.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total_pendiente_cobro = sum((m.saldo for m in multas_pendientes), Decimal('0.00'))
    total_condonado = sum((m.monto for m in multas_condonadas), Decimal('0.00'))

    # Últimos pagos registrados en mostrador
    ultimos_pagos = Pago.objects.select_related(
        'multa__usuario', 'multa__prestamo__ejemplar__libro', 'registrado_por'
    ).order_by('-fecha_pago', '-id')[:20]

    contexto = {
        'usuario': request.user,
        'titulo': 'Reportes de la biblioteca',
        'fecha_inicio': fecha_inicio.isoformat(),
        'fecha_fin': fecha_fin.isoformat(),
        'fecha_inicio_obj': fecha_inicio,
        'fecha_fin_obj': fecha_fin,
        # Reporte 1
        'prestamos_periodo': prestamos_periodo[:50],
        'total_prestamos_periodo': prestamos_periodo.count(),
        'resumen_periodo': resumen_periodo,
        'prestamos_estudiantes': conteo_roles.get('ESTUDIANTE', 0),
        'prestamos_profesores': conteo_roles.get('PROFESOR', 0),
        # Reporte 2
        'libros_mas_solicitados': libros_mas_solicitados,
        # Reporte 3
        'prestamos_vencidos': prestamos_vencidos,
        # Reporte 4
        'multas_pendientes': multas_pendientes,
        'multas_pagadas_count': len(multas_pagadas),
        'multas_condonadas_count': len(multas_condonadas),
        'total_cobrado': total_cobrado,
        'total_pendiente_cobro': total_pendiente_cobro,
        'total_condonado': total_condonado,
        'ultimos_pagos': ultimos_pagos,
    }

    return render(request, 'reportes/reportes.html', contexto)
