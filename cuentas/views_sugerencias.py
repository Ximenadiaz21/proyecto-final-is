from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notificacion, Profesor, SugerenciaAdquisicion
from .views_usuarios import bibliotecario_requerido


# Permite a un profesor enviar sugerencias de adquisición y consultar las enviadas (CU-16, RF-16)
@login_required
def mis_sugerencias(request):
    usuario = request.user

    # 1. Verifica que el usuario sea un profesor activo y no bloqueado
    if usuario.tipo_usuario != 'PROFESOR':
        messages.error(request, "Solo los profesores pueden enviar sugerencias de adquisición.")
        return redirect('panel')

    if usuario.bloqueado:
        messages.error(request, "Tu cuenta está bloqueada. No puedes enviar sugerencias.")
        return redirect('panel')

    # 2. Obtiene el perfil de profesor asociado al usuario
    profesor = Profesor.objects.filter(usuario=usuario).first()
    if not profesor:
        messages.error(request, "Tu cuenta no tiene un perfil de profesor configurado.")
        return redirect('panel')

    # Valores iniciales del formulario en caso de error de validación
    datos_previos = {
        'titulo': '',
        'autores': '',
        'isbn': '',
        'justificacion': '',
    }

    # 3. Si el profesor envía el formulario por POST, valida y registra la sugerencia
    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        autores = request.POST.get('autores', '').strip()
        isbn = request.POST.get('isbn', '').strip().replace('-', '').replace(' ', '')
        justificacion = request.POST.get('justificacion', '').strip()

        datos_previos = {
            'titulo': titulo,
            'autores': autores,
            'isbn': isbn,
            'justificacion': justificacion,
        }

        # Valida los campos obligatorios y sus longitudes
        if not titulo or not autores or not justificacion:
            messages.error(
                request,
                "Por favor completa los campos obligatorios: título, autor(es) y justificación."
            )
        elif len(titulo) > 255 or len(autores) > 255:
            messages.error(request, "El título y los autores no pueden exceder de 255 caracteres.")
        elif isbn and (not isbn.isdigit() or len(isbn) not in (10, 13)):
            messages.error(
                request,
                "El ISBN es opcional, pero si lo indicas debe tener 10 o 13 dígitos sin guiones."
            )
        else:
            # Guarda la propuesta en estado PENDIENTE
            sugerencia = SugerenciaAdquisicion.objects.create(
                profesor=profesor,
                titulo=titulo,
                autores=autores,
                isbn=isbn or None,
                justificacion=justificacion,
                estado='PENDIENTE',
                fecha=timezone.now()
            )

            messages.success(
                request,
                f"Tu sugerencia para adquirir «{sugerencia.titulo}» fue enviada al bibliotecario."
            )
            return redirect('mis_sugerencias')

    # 4. Consulta el historial de sugerencias enviadas por este profesor
    sugerencias = SugerenciaAdquisicion.objects.filter(
        profesor=profesor
    ).order_by('-fecha', '-id')

    contexto = {
        'usuario': usuario,
        'titulo': 'Sugerir adquisición de libro',
        'sugerencias': sugerencias,
        'datos': datos_previos,
    }

    return render(request, 'sugerencias/mis_sugerencias.html', contexto)


# Muestra al bibliotecario las sugerencias de adquisición pendientes y atendidas (CU-33, RF-16)
@bibliotecario_requerido
def gestion_sugerencias(request):
    # Consulta todas las sugerencias con los datos del profesor y su departamento
    base = SugerenciaAdquisicion.objects.select_related(
        'profesor__usuario',
        'profesor__departamento'
    )

    # Separa las propuestas pendientes de revisión y el historial ya atendido
    pendientes = base.filter(estado='PENDIENTE').order_by('fecha', 'id')
    historial = base.exclude(estado='PENDIENTE').order_by('-fecha', '-id')[:30]

    contexto = {
        'usuario': request.user,
        'titulo': 'Sugerencias de adquisición',
        'pendientes': pendientes,
        'historial': historial,
    }

    return render(request, 'sugerencias/gestion_sugerencias.html', contexto)


# Permite al bibliotecario aprobar o rechazar una sugerencia de adquisición (CU-33, RF-16)
@bibliotecario_requerido
@require_POST
def responder_sugerencia(request, sugerencia_id):
    nuevo_estado = request.POST.get('estado', '').strip()
    respuesta = request.POST.get('respuesta', '').strip()

    # 1. Verifica que la decisión sea APROBADA o RECHAZADA
    if nuevo_estado not in ('APROBADA', 'RECHAZADA'):
        messages.error(request, "Debes seleccionar si apruebas o rechazas la sugerencia.")
        return redirect('gestion_sugerencias')

    # 2. Exige un comentario cuando se rechaza la propuesta y valida la longitud máxima
    if nuevo_estado == 'RECHAZADA' and not respuesta:
        messages.error(request, "Escribe el motivo por el cual se rechaza la sugerencia.")
        return redirect('gestion_sugerencias')

    if len(respuesta) > 255:
        messages.error(request, "La respuesta no puede exceder de 255 caracteres.")
        return redirect('gestion_sugerencias')

    # 3. Actualiza la sugerencia y notifica al profesor dentro de una transacción atómica
    with transaction.atomic():
        sugerencia = get_object_or_404(
            SugerenciaAdquisicion.objects.select_for_update().select_related('profesor__usuario'),
            id=sugerencia_id
        )

        if sugerencia.estado != 'PENDIENTE':
            messages.error(request, "Esta sugerencia ya fue atendida anteriormente.")
            return redirect('gestion_sugerencias')

        sugerencia.estado = nuevo_estado
        sugerencia.respuesta = respuesta or None
        sugerencia.save(update_fields=['estado', 'respuesta'])

        # Envía notificación al profesor informando el dictamen de la biblioteca
        verbo = 'aprobada' if nuevo_estado == 'APROBADA' else 'rechazada'
        detalle_respuesta = f" Respuesta de biblioteca: {respuesta}" if respuesta else ""

        Notificacion.objects.create(
            usuario=sugerencia.profesor.usuario,
            tipo='GENERAL',
            mensaje=(
                f"Tu sugerencia de adquisición para «{sugerencia.titulo}» fue {verbo}."
                f"{detalle_respuesta}"
            )[:500],
            leida=False,
            fecha=timezone.now()
        )

    etiqueta = 'aprobada' if nuevo_estado == 'APROBADA' else 'rechazada'
    messages.success(
        request,
        f"La sugerencia «{sugerencia.titulo}» fue {etiqueta} correctamente."
    )
    return redirect('gestion_sugerencias')
