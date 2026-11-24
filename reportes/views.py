import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from catalogo.models import Libro
from cuentas.permisos import bibliotecario_requerido
from multas.models import Multa, Pago
from multas.views import con_saldos
from prestamos.models import Prestamo


# Estados de préstamo considerados efectivos para estadísticas de demanda (excluye cancelados/expirados)
ESTADOS_PRESTAMO_EFECTIVO = ['ACTIVO', 'VENCIDO', 'DEVUELTO', 'PERDIDO']

# Estados de reserva considerados efectivos para el conteo de demanda
ESTADOS_RESERVA_EFECTIVA = ['PENDIENTE', 'DISPONIBLE', 'ATENDIDA']


# Convierte una cadena YYYY-MM-DD a objeto date; devuelve None si no es válida
def _parsear_fecha(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


# Obtiene el rango de fechas solicitado en GET (por defecto últimos 30 días)
def _rango_fechas(request):
    hoy = timezone.localdate()
    inicio_str = request.GET.get('fecha_inicio', '').strip()
    fin_str = request.GET.get('fecha_fin', '').strip()

    fecha_fin = _parsear_fecha(fin_str) or hoy
    fecha_inicio = _parsear_fecha(inicio_str) or (fecha_fin - timedelta(days=30))

    if fecha_inicio > fecha_fin:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio

    inicio_dt = timezone.make_aware(datetime.combine(fecha_inicio, time.min))
    fin_dt = timezone.make_aware(datetime.combine(fecha_fin, time.max))
    return hoy, fecha_inicio, fecha_fin, inicio_dt, fin_dt


# Consulta base del reporte 1: préstamos en el periodo
def _prestamos_en_periodo(inicio_dt, fin_dt):
    return Prestamo.objects.filter(
        fecha_solicitud__gte=inicio_dt,
        fecha_solicitud__lte=fin_dt,
    ).select_related(
        'usuario', 'ejemplar', 'ejemplar__libro'
    ).order_by('-fecha_solicitud', '-id')


# Consulta base del reporte 2: libros más solicitados (excluye cancelados y expirados)
def _libros_mas_solicitados():
    return Libro.objects.select_related(
        'editorial', 'categoria'
    ).annotate(
        total_prestamos=Count(
            'ejemplar__prestamo',
            filter=Q(ejemplar__prestamo__estado__in=ESTADOS_PRESTAMO_EFECTIVO),
            distinct=True,
        ),
        total_reservas=Count(
            'reserva',
            filter=Q(reserva__estado__in=ESTADOS_RESERVA_EFECTIVA),
            distinct=True,
        ),
    ).filter(
        Q(total_prestamos__gt=0) | Q(total_reservas__gt=0)
    ).order_by('-total_prestamos', '-total_reservas', 'titulo')


# Consulta base del reporte 3: préstamos vencidos actualmente
def _prestamos_vencidos(hoy):
    lista = list(
        Prestamo.objects.filter(
            Q(estado='VENCIDO') | Q(estado='ACTIVO', fecha_vencimiento__lt=hoy)
        ).select_related(
            'usuario', 'ejemplar', 'ejemplar__libro'
        ).order_by('fecha_vencimiento', 'id')
    )
    for p in lista:
        p.retraso_actual = p.dias_retraso(hoy)
    return lista


# Genera los 4 reportes operativos requeridos por la biblioteca (CU-32, RF-14)
@bibliotecario_requerido
def reportes(request):
    hoy, fecha_inicio, fecha_fin, inicio_dt, fin_dt = _rango_fechas(request)

    # Reporte 1: Préstamos por periodo
    prestamos_periodo = _prestamos_en_periodo(inicio_dt, fin_dt)
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

    # Reporte 2: Libros más solicitados
    libros_mas_solicitados = _libros_mas_solicitados()[:10]

    # Reporte 3: Préstamos vencidos
    prestamos_vencidos = _prestamos_vencidos(hoy)

    # Reporte 4: Multas cobradas y pendientes (con_saldos calcula pagado y saldo en una consulta SQL)
    multas_todas = con_saldos(
        Multa.objects.select_related(
            'usuario', 'prestamo__ejemplar__libro'
        ).order_by('-fecha_generacion', '-id')
    )
    multas_pendientes = [m for m in multas_todas if m.estado == 'PENDIENTE']
    multas_pagadas = [m for m in multas_todas if m.estado == 'PAGADA']
    multas_condonadas = [m for m in multas_todas if m.estado == 'CONDONADA']

    # Total cobrado = suma real de pagos; total condonado = saldo perdonado (sin doble conteo)
    total_cobrado = Pago.objects.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total_pendiente_cobro = sum((m.saldo for m in multas_pendientes), Decimal('0.00'))
    total_condonado = sum((max(m.saldo, Decimal('0.00')) for m in multas_condonadas), Decimal('0.00'))

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
        'prestamos_periodo': prestamos_periodo[:50],
        'total_prestamos_periodo': prestamos_periodo.count(),
        'resumen_periodo': resumen_periodo,
        'prestamos_estudiantes': conteo_roles.get('ESTUDIANTE', 0),
        'prestamos_profesores': conteo_roles.get('PROFESOR', 0),
        'libros_mas_solicitados': libros_mas_solicitados,
        'prestamos_vencidos': prestamos_vencidos,
        'multas_pendientes': multas_pendientes,
        'multas_pagadas_count': len(multas_pagadas),
        'multas_condonadas_count': len(multas_condonadas),
        'total_cobrado': total_cobrado,
        'total_pendiente_cobro': total_pendiente_cobro,
        'total_condonado': total_condonado,
        'ultimos_pagos': ultimos_pagos,
    }
    return render(request, 'reportes/reportes.html', contexto)


# Exporta cualquiera de los 4 reportes a CSV con BOM UTF-8 compatible con Excel (CU-32, RF-14)
@bibliotecario_requerido
def exportar_reporte_csv(request, tipo):
    hoy, fecha_inicio, fecha_fin, inicio_dt, fin_dt = _rango_fechas(request)

    if tipo not in ('prestamos', 'libros', 'vencidos', 'multas'):
        raise Http404("Tipo de reporte no válido.")

    # Configura la respuesta como descarga CSV con BOM UTF-8 para abrir acentos en Excel
    nombre_archivo = f"reporte_{tipo}_{hoy.isoformat()}.csv"
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    respuesta.write('\ufeff')
    escritor = csv.writer(respuesta)

    if tipo == 'prestamos':
        escritor.writerow([
            'Folio', 'Fecha solicitud', 'Usuario', 'Rol',
            'Libro', 'Ejemplar', 'Vencimiento', 'Estado',
        ])
        for p in _prestamos_en_periodo(inicio_dt, fin_dt):
            escritor.writerow([
                p.id,
                timezone.localtime(p.fecha_solicitud).strftime('%Y-%m-%d %H:%M'),
                p.usuario.username,
                p.usuario.get_tipo_usuario_display(),
                p.ejemplar.libro.titulo,
                p.ejemplar.codigo_inventario,
                p.fecha_vencimiento.isoformat() if p.fecha_vencimiento else '',
                p.estado,
            ])

    elif tipo == 'libros':
        escritor.writerow([
            'Posicion', 'Titulo', 'ISBN', 'Categoria', 'Editorial', 'Prestamos', 'Reservas',
        ])
        for idx, libro in enumerate(_libros_mas_solicitados()[:50], start=1):
            escritor.writerow([
                idx,
                libro.titulo,
                libro.isbn,
                libro.categoria.nombre,
                libro.editorial.nombre,
                libro.total_prestamos,
                libro.total_reservas,
            ])

    elif tipo == 'vencidos':
        escritor.writerow([
            'Folio', 'Usuario', 'Nombre', 'Correo', 'Libro',
            'Ejemplar', 'Fecha vencimiento', 'Dias retraso',
        ])
        for p in _prestamos_vencidos(hoy):
            escritor.writerow([
                p.id,
                p.usuario.username,
                p.usuario.get_full_name() or p.usuario.username,
                p.usuario.email,
                p.ejemplar.libro.titulo,
                p.ejemplar.codigo_inventario,
                p.fecha_vencimiento.isoformat() if p.fecha_vencimiento else '',
                p.retraso_actual,
            ])

    elif tipo == 'multas':
        escritor.writerow([
            'ID', 'Usuario', 'Libro', 'Motivo', 'Estado',
            'Monto', 'Pagado', 'Saldo', 'Fecha generacion',
        ])
        multas = con_saldos(
            Multa.objects.select_related('usuario', 'prestamo__ejemplar__libro')
            .order_by('-fecha_generacion', '-id')
        )
        for m in multas:
            escritor.writerow([
                m.id,
                m.usuario.username,
                m.prestamo.ejemplar.libro.titulo,
                m.get_motivo_display(),
                m.estado,
                f"{m.monto:.2f}",
                f"{m.pagado:.2f}",
                f"{m.saldo:.2f}",
                timezone.localtime(m.fecha_generacion).strftime('%Y-%m-%d %H:%M'),
            ])

    return respuesta
