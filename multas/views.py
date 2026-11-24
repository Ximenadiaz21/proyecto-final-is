from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cuentas.permisos import bibliotecario_requerido, lector_requerido
from prestamos.servicios import ReglaNegocioError
from . import servicios
from .models import Multa


# Calcula cuánto se ha pagado de una multa
def total_pagado(multa):
    return multa.total_pagado()


# Agrega pagado y saldo a cada multa en una sola consulta SQL
def con_saldos(multas):
    if hasattr(multas, 'annotate') and not multas.query.is_sliced:
        multas = multas.annotate(
            pagado=Coalesce(Sum('pago__monto'), Decimal('0.00'))
        )
    lista = list(multas)
    for m in lista:
        if not hasattr(m, 'pagado') or m.pagado is None:
            m.pagado = m.total_pagado()
        m.saldo = m.monto - m.pagado
    return lista


# Muestra las multas del usuario que inició sesión (CU-14)
@lector_requerido
def mis_multas(request):
    usuario = request.user

    multas = con_saldos(
        Multa.objects.filter(usuario=usuario).select_related(
            'prestamo__ejemplar__libro'
        ).order_by('-fecha_generacion')
    )

    pendientes = [m for m in multas if m.estado == 'PENDIENTE']
    historial_lista = [m for m in multas if m.estado != 'PENDIENTE']
    historial = Paginator(historial_lista, 10).get_page(request.GET.get('page'))
    total_adeudado = sum((m.saldo for m in pendientes), Decimal('0'))

    contexto = {
        'usuario': usuario,
        'titulo': 'Mis multas',
        'pendientes': pendientes,
        'historial': historial,
        'total_adeudado': total_adeudado,
    }

    return render(request, 'multas/mis_multas.html', contexto)


# Muestra las multas para que el bibliotecario cobre o condone
@bibliotecario_requerido
def gestion_multas(request):
    base = Multa.objects.select_related(
        'usuario', 'prestamo__ejemplar__libro'
    ).annotate(
        pagado=Coalesce(Sum('pago__monto'), Decimal('0.00'))
    )

    pendientes = con_saldos(base.filter(estado='PENDIENTE').order_by('fecha_generacion'))
    historial_pagina = Paginator(
        base.exclude(estado='PENDIENTE').order_by('-fecha_generacion', '-id'),
        15
    ).get_page(request.GET.get('page'))
    historial_pagina.object_list = con_saldos(historial_pagina.object_list)

    contexto = {
        'usuario': request.user,
        'titulo': 'Multas y pagos',
        'pendientes': pendientes,
        'historial': historial_pagina,
        'total_pendiente': sum((m.saldo for m in pendientes), Decimal('0')),
    }

    return render(request, 'multas/gestion_multas.html', contexto)


# Registra un pago total o parcial (CU-28); delega reglas y transacción a multas/servicios.py
@bibliotecario_requerido
@require_POST
def registrar_pago(request, multa_id):
    metodo = request.POST.get('metodo', '')
    monto = request.POST.get('monto', '')

    try:
        pago, _ = servicios.registrar_pago(multa_id, monto, metodo, request.user)
    except Multa.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_multas')

    messages.success(request, f"Pago de ${pago.monto:.2f} registrado. Folio: {pago.folio_recibo}.")
    return redirect('gestion_multas')


# Condona una multa con justificación obligatoria (RN-14, CU-29); delega a multas/servicios.py
@bibliotecario_requerido
@require_POST
def condonar_multa(request, multa_id):
    justificacion = request.POST.get('justificacion', '')

    try:
        servicios.condonar_multa(multa_id, justificacion, request.user)
    except Multa.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_multas')

    messages.success(request, "Multa condonada correctamente.")
    return redirect('gestion_multas')