from django.shortcuts import render

# Create your views here.
from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Multa, Pago

METODOS_VALIDOS = ['EFECTIVO', 'TARJETA', 'TRANSFERENCIA']


# Revisa que el usuario sea bibliotecario activo y no esté bloqueado
def es_bibliotecario(usuario):
    return usuario.tipo_usuario == 'BIBLIOTECARIO' and not usuario.bloqueado


# Calcula cuánto se ha pagado de una multa
def total_pagado(multa):
    return multa.pago_set.aggregate(t=Sum('monto'))['t'] or Decimal('0')


# Agrega pagado y saldo a cada multa para mostrarlos en las plantillas
def con_saldos(multas):
    lista = list(multas)
    for m in lista:
        m.pagado = total_pagado(m)
        m.saldo = m.monto - m.pagado
    return lista


# Muestra las multas del usuario que inició sesión (CU-14)
@login_required
def mis_multas(request):
    usuario = request.user

    if usuario.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Esta sección es solo para estudiantes y profesores.")
        return redirect('panel')

    multas = con_saldos(
        Multa.objects.filter(usuario=usuario).select_related(
            'prestamo__ejemplar__libro'
        ).order_by('-fecha_generacion')
    )

    pendientes = [m for m in multas if m.estado == 'PENDIENTE']
    historial = [m for m in multas if m.estado != 'PENDIENTE']
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
@login_required
def gestion_multas(request):
    if not es_bibliotecario(request.user):
        messages.error(request, "Esta sección es solo para bibliotecarios.")
        return redirect('panel')

    base = Multa.objects.select_related('usuario', 'prestamo__ejemplar__libro')

    pendientes = con_saldos(base.filter(estado='PENDIENTE').order_by('fecha_generacion'))
    historial = con_saldos(base.exclude(estado='PENDIENTE').order_by('-fecha_generacion')[:20])

    contexto = {
        'usuario': request.user,
        'titulo': 'Multas y pagos',
        'pendientes': pendientes,
        'historial': historial,
        'total_pendiente': sum((m.saldo for m in pendientes), Decimal('0')),
    }

    return render(request, 'multas/gestion_multas.html', contexto)


# Registra un pago total o parcial (CU-28)
@login_required
@require_POST
def registrar_pago(request, multa_id):
    if not es_bibliotecario(request.user):
        messages.error(request, "No tienes permiso para registrar pagos.")
        return redirect('panel')

    metodo = request.POST.get('metodo', '')
    if metodo not in METODOS_VALIDOS:
        messages.error(request, "Selecciona un método de pago válido.")
        return redirect('gestion_multas')

    try:
        monto = Decimal(request.POST.get('monto', '')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        messages.error(request, "El monto no es válido.")
        return redirect('gestion_multas')

    with transaction.atomic():
        multa = get_object_or_404(Multa.objects.select_for_update(), id=multa_id)

        if multa.estado != 'PENDIENTE':
            messages.error(request, "Esta multa ya no está pendiente.")
            return redirect('gestion_multas')

        saldo = multa.monto - total_pagado(multa)

        if monto <= 0 or monto > saldo:
            messages.error(request, f"El monto debe ser mayor a $0.00 y no puede exceder el saldo (${saldo:.2f}).")
            return redirect('gestion_multas')

        ahora = timezone.now()
        num_pago = multa.pago_set.count() + 1
        folio = f"REC-{timezone.localtime(ahora):%Y%m%d%H%M%S}-{multa.id}-{num_pago}"

        Pago.objects.create(
            multa=multa,
            monto=monto,
            metodo=metodo,
            folio_recibo=folio,
            fecha_pago=ahora,
            registrado_por=request.user
        )

        # Si ya se pagó todo, la multa queda PAGADA
        if monto == saldo:
            multa.estado = 'PAGADA'
            multa.save()

    messages.success(request, f"Pago de ${monto:.2f} registrado. Folio: {folio}.")
    return redirect('gestion_multas')


# Condona una multa con justificación obligatoria (RN-14, CU-29)
@login_required
@require_POST
def condonar_multa(request, multa_id):
    if not es_bibliotecario(request.user):
        messages.error(request, "Solo el bibliotecario puede condonar multas.")
        return redirect('panel')

    justificacion = request.POST.get('justificacion', '').strip()

    if not justificacion:
        messages.error(request, "Debes escribir una justificación para condonar la multa (RN-14).")
        return redirect('gestion_multas')

    if len(justificacion) > 255:
        messages.error(request, "La justificación no puede pasar de 255 caracteres.")
        return redirect('gestion_multas')

    with transaction.atomic():
        multa = get_object_or_404(Multa.objects.select_for_update(), id=multa_id)

        if multa.estado != 'PENDIENTE':
            messages.error(request, "Esta multa ya no está pendiente.")
            return redirect('gestion_multas')

        multa.estado = 'CONDONADA'
        multa.justificacion_condonacion = justificacion
        multa.condonada_por = request.user
        multa.save()

    messages.success(request, "Multa condonada correctamente.")
    return redirect('gestion_multas')