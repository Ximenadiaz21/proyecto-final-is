
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notificacion


# Muestra el panel del usuario
@login_required
def panel_usuario(request):

    # Obtén el usuario que inició sesión
    usuario = request.user

    # Revisa el tipo de usuario
    if usuario.tipo_usuario == 'ESTUDIANTE':
        titulo = 'Panel del estudiante'

    elif usuario.tipo_usuario == 'PROFESOR':
        titulo = 'Panel del profesor'

    elif usuario.tipo_usuario == 'BIBLIOTECARIO':
        titulo = 'Panel del bibliotecario'

    else:
        titulo = 'Panel de usuario'

    # Envía los datos al HTML (notificaciones_no_leidas ya lo inyecta el context processor)
    contexto = {
        'usuario': usuario,
        'titulo': titulo,
    }

    return render(request, 'panel.html', contexto)


# Muestra las notificaciones del usuario autenticado (CU-15, RF-15)
@login_required
def mis_notificaciones(request):
    # Obtiene el usuario que tiene la sesión activa
    usuario = request.user

    # Consulta notificaciones no leídas y pagina el historial de leídas (RNF-05)
    no_leidas = list(
        Notificacion.objects.filter(usuario=usuario, leida=False).order_by('-fecha', '-id')
    )
    leidas_qs = Notificacion.objects.filter(usuario=usuario, leida=True).order_by('-fecha', '-id')
    leidas_pagina = Paginator(leidas_qs, 10).get_page(request.GET.get('page'))

    # Prepara el contexto para enviar a la plantilla HTML
    contexto = {
        'usuario': usuario,
        'titulo': 'Mis notificaciones',
        'no_leidas': no_leidas,
        'leidas': leidas_pagina,
        'total_no_leidas': len(no_leidas),
    }

    return render(request, 'notificaciones/mis_notificaciones.html', contexto)


# Marca una notificación individual del usuario como leída (CU-15)
@login_required
@require_POST
def marcar_notificacion_leida(request, notificacion_id):
    # Busca la notificación asegurando que pertenezca al usuario en sesión (RNF-02)
    notificacion = get_object_or_404(
        Notificacion,
        id=notificacion_id,
        usuario=request.user
    )

    # Actualiza el estado únicamente si aún estaba pendiente por leer
    if not notificacion.leida:
        notificacion.leida = True
        notificacion.save(update_fields=['leida'])
        messages.success(request, "Notificación marcada como leída.")

    return redirect('mis_notificaciones')


# Marca todas las notificaciones pendientes del usuario como leídas (CU-15)
@login_required
@require_POST
def marcar_todas_leidas(request):
    # Actualiza en bloque todas las notificaciones no leídas del usuario actual
    actualizadas = Notificacion.objects.filter(
        usuario=request.user,
        leida=False
    ).update(leida=True)

    # Informa al usuario el resultado de la acción
    if actualizadas:
        messages.success(request, f"Se marcaron {actualizadas} notificación(es) como leídas.")
    else:
        messages.info(request, "No tenías notificaciones pendientes por leer.")

    return redirect('mis_notificaciones')

