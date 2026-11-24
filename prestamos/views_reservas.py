from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Ejemplar, Libro
from cuentas.models import Notificacion, Usuario
from cuentas.views_usuarios import bibliotecario_requerido
from .models import PoliticaPrestamo, Prestamo, Reserva
from .reglas import liberar_o_asignar_ejemplar, libros_en_uso, motivo_inelegible


# Permite a un estudiante o profesor reservar un libro sin ejemplares disponibles (CU-11)
@login_required
@require_POST
def reservar_libro(request, libro_id):
    libro = get_object_or_404(Libro, id=libro_id, activo=True)

    # 1. Solo estudiantes y profesores pueden reservar libros
    if request.user.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Los bibliotecarios no pueden reservar libros.")
        return redirect('detalle_libro', libro_id=libro.id)

    with transaction.atomic():
        # Bloquea al usuario dentro de la transacción para evitar reservas duplicadas concurrentes (RNF-03)
        usuario = Usuario.objects.select_for_update().get(pk=request.user.pk)

        if not usuario.is_active:
            messages.error(request, "Tu cuenta no está activa. Contacta al personal de la biblioteca.")
            return redirect('detalle_libro', libro_id=libro.id)

        # 2. Verifica elegibilidad: cuenta activa, sin multas pendientes ni préstamos vencidos (CU-07, RN-08)
        motivo = motivo_inelegible(usuario)
        if motivo:
            messages.error(request, motivo)
            return redirect('detalle_libro', libro_id=libro.id)

        # 3. Solo se puede reservar cuando NO hay ejemplares disponibles (RF-09, CU-06 2a)
        ejemplares_libro = Ejemplar.objects.select_for_update().filter(libro=libro)
        hay_disponibles = ejemplares_libro.filter(estado='DISPONIBLE').exists()

        if hay_disponibles:
            messages.info(
                request,
                "Este libro sí tiene ejemplares disponibles. Puedes solicitar el préstamo directamente."
            )
            return redirect('detalle_libro', libro_id=libro.id)

        # Verifica que exista al menos un ejemplar en circulación que pueda liberarse (evita reservas imposibles)
        hay_en_circulacion = ejemplares_libro.filter(
            estado__in=['PRESTADO', 'RESERVADO', 'EN_REPARACION']
        ).exists()
        if not hay_en_circulacion:
            messages.error(
                request,
                "Este título no cuenta con ejemplares activos en circulación para poder reservarlo."
            )
            return redirect('detalle_libro', libro_id=libro.id)

        # 4. Evita reservar un libro que el usuario ya tiene en préstamo (RN-11)
        tiene_prestamo = Prestamo.objects.filter(
            usuario=usuario,
            ejemplar__libro=libro,
            estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
        ).exists()

        if tiene_prestamo:
            messages.error(request, "Ya tienes un préstamo activo o solicitado de este mismo título (RN-11).")
            return redirect('detalle_libro', libro_id=libro.id)

        # 5. Evita duplicar reservas activas del mismo título por el mismo usuario
        tiene_reserva = Reserva.objects.filter(
            usuario=usuario,
            libro=libro,
            estado__in=['PENDIENTE', 'DISPONIBLE']
        ).exists()

        if tiene_reserva:
            messages.error(request, "Ya tienes una reserva activa para este libro.")
            return redirect('mis_prestamos')

        ahora = timezone.now()

        # 6. Registra la reserva en la cola FIFO (RN-12)
        reserva = Reserva.objects.create(
            usuario=usuario,
            libro=libro,
            estado='PENDIENTE',
            fecha_reserva=ahora
        )

        # Calcula la posición exacta del usuario en la cola FIFO (mismo desempate por id que liberar_o_asignar_ejemplar)
        posicion = Reserva.objects.filter(
            libro=libro,
            estado='PENDIENTE',
        ).filter(
            Q(fecha_reserva__lt=reserva.fecha_reserva)
            | Q(fecha_reserva=reserva.fecha_reserva, id__lte=reserva.id)
        ).count()

        # Genera notificación de confirmación para el usuario
        Notificacion.objects.create(
            usuario=usuario,
            tipo='GENERAL',
            mensaje=(
                f"Reserva #{reserva.id} de \"{libro.titulo}\" registrada en la cola de espera "
                f"(posición {posicion}). Te notificaremos cuando un ejemplar esté disponible."
            ),
            leida=False,
            fecha=ahora
        )

    messages.success(
        request,
        f"¡Reserva registrada para \"{libro.titulo}\"! Tu lugar en la cola de espera es el #{posicion}."
    )
    return redirect('mis_prestamos')


# Permite al usuario lector cancelar su propia reserva (CU-12)
@login_required
@require_POST
def cancelar_reserva(request, reserva_id):
    with transaction.atomic():
        # Solo puede cancelar sus propias reservas
        reserva = get_object_or_404(
            Reserva.objects.select_for_update().select_related('ejemplar_asignado', 'ejemplar_asignado__libro'),
            id=reserva_id,
            usuario=request.user
        )

        if reserva.estado not in ['PENDIENTE', 'DISPONIBLE']:
            messages.error(request, "Solo se pueden cancelar reservas pendientes o disponibles.")
            return redirect('mis_prestamos')

        ejemplar = reserva.ejemplar_asignado

        reserva.estado = 'CANCELADA'
        reserva.ejemplar_asignado = None
        reserva.save(update_fields=['estado', 'ejemplar_asignado'])

        # Si ya tenía un ejemplar apartado, se asigna al siguiente en la cola FIFO o queda DISPONIBLE (RN-12)
        if ejemplar:
            ejemplar_bloqueado = Ejemplar.objects.select_for_update().select_related('libro').get(pk=ejemplar.pk)
            liberar_o_asignar_ejemplar(ejemplar_bloqueado, timezone.now())

    messages.success(request, "Tu reserva ha sido cancelada correctamente.")
    return redirect('mis_prestamos')


# Panel del bibliotecario para consultar y atender las reservas (CU-30)
@bibliotecario_requerido
def gestion_reservas(request):
    # Reservas que ya tienen ejemplar apartado esperando a que el lector lo recoja
    disponibles = Reserva.objects.filter(
        estado='DISPONIBLE'
    ).select_related(
        'usuario', 'libro', 'ejemplar_asignado'
    ).order_by('fecha_expiracion')

    # Cola de espera en orden de llegada FIFO (RN-12)
    pendientes = Reserva.objects.filter(
        estado='PENDIENTE'
    ).select_related(
        'usuario', 'libro'
    ).order_by('fecha_reserva', 'id')

    # Últimas reservas finalizadas para consulta de historial
    historial = Reserva.objects.filter(
        estado__in=['ATENDIDA', 'CANCELADA', 'EXPIRADA']
    ).select_related(
        'usuario', 'libro', 'ejemplar_asignado'
    ).order_by('-fecha_reserva')[:20]

    contexto = {
        'usuario': request.user,
        'titulo': 'Gestión de reservas',
        'disponibles': disponibles,
        'pendientes': pendientes,
        'historial': historial,
    }

    return render(request, 'prestamos/gestion_reservas.html', contexto)


# El bibliotecario entrega el ejemplar apartado de una reserva DISPONIBLE y crea el préstamo ACTIVO (CU-30)
@bibliotecario_requerido
@require_POST
def atender_reserva(request, reserva_id):
    with transaction.atomic():
        reserva = get_object_or_404(
            Reserva.objects.select_for_update().select_related('usuario', 'libro', 'ejemplar_asignado'),
            id=reserva_id
        )

        if reserva.estado != 'DISPONIBLE' or not reserva.ejemplar_asignado:
            messages.error(request, "Esta reserva no tiene un ejemplar disponible para entregar.")
            return redirect('gestion_reservas')

        ahora = timezone.now()

        # RN-06: Si ya venció el plazo de recogida, marca la reserva como EXPIRADA y libera/reasigna el ejemplar
        if reserva.fecha_expiracion and reserva.fecha_expiracion < ahora:
            ejemplar_exp = Ejemplar.objects.select_for_update().select_related('libro').get(
                pk=reserva.ejemplar_asignado_id
            )
            reserva.estado = 'EXPIRADA'
            reserva.save(update_fields=['estado'])
            if ejemplar_exp.estado == 'RESERVADO':
                liberar_o_asignar_ejemplar(ejemplar_exp, ahora)
            messages.error(
                request,
                f"La reserva #{reserva.id} expiró porque venció su plazo para recoger (RN-06). "
                "El ejemplar fue liberado o asignado al siguiente usuario en cola."
            )
            return redirect('gestion_reservas')

        lector = Usuario.objects.select_for_update().get(pk=reserva.usuario_id)

        if not lector.is_active:
            messages.error(
                request,
                f"No se puede entregar al usuario {lector.username} porque su cuenta está inactiva."
            )
            return redirect('gestion_reservas')

        # 1. Re-verifica elegibilidad al momento de entregar (CU-07, RN-08)
        motivo = motivo_inelegible(lector)
        if motivo:
            messages.error(request, f"No se puede entregar al usuario {lector.username}: {motivo}")
            return redirect('gestion_reservas')

        # 2. Obtiene la política de préstamo según el tipo de usuario
        try:
            politica = PoliticaPrestamo.objects.get(tipo_usuario=lector.tipo_usuario)
        except PoliticaPrestamo.DoesNotExist:
            messages.error(request, "No hay política de préstamo configurada para este tipo de usuario.")
            return redirect('gestion_reservas')

        # 3. Verifica el límite de libros simultáneos sin contar esta misma reserva (RN-02)
        prestamos_activos = libros_en_uso(lector, excluir_reserva_id=reserva.id)

        if prestamos_activos >= politica.max_libros:
            messages.error(
                request,
                f"El usuario {lector.username} ya alcanzó su límite de libros ({politica.max_libros}) (RN-02)."
            )
            return redirect('gestion_reservas')

        # 4. Evita prestar dos veces el mismo título al mismo usuario (RN-11)
        if Prestamo.objects.filter(
            usuario=lector,
            ejemplar__libro=reserva.libro,
            estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
        ).exists():
            messages.error(
                request,
                f"El usuario {lector.username} ya tiene un préstamo activo de este título (RN-11)."
            )
            return redirect('gestion_reservas')

        ahora = timezone.now()
        vencimiento = timezone.localdate() + timedelta(days=politica.dias_prestamo)
        ejemplar = Ejemplar.objects.select_for_update().get(pk=reserva.ejemplar_asignado_id)

        if ejemplar.estado != 'RESERVADO':
            messages.error(
                request,
                f"El ejemplar [{ejemplar.codigo_inventario}] no está apartado (estado actual: {ejemplar.estado})."
            )
            return redirect('gestion_reservas')

        # 5. Registra el préstamo como ACTIVO y marca el ejemplar como PRESTADO
        Prestamo.objects.create(
            usuario=lector,
            ejemplar=ejemplar,
            estado='ACTIVO',
            fecha_solicitud=reserva.fecha_reserva,
            fecha_prestamo=ahora,
            fecha_vencimiento=vencimiento,
            num_renovaciones=0,
            entregado_por=request.user
        )

        ejemplar.estado = 'PRESTADO'
        ejemplar.save(update_fields=['estado'])

        reserva.estado = 'ATENDIDA'
        reserva.save(update_fields=['estado'])

    messages.success(
        request,
        f"Reserva atendida: ejemplar [{ejemplar.codigo_inventario}] entregado a {lector.username}. "
        f"Fecha de devolución: {vencimiento.strftime('%d/%m/%Y')}."
    )
    return redirect('gestion_reservas')


# Permite al bibliotecario cancelar una reserva activa y liberar/reasignar su ejemplar (CU-30)
@bibliotecario_requerido
@require_POST
def cancelar_reserva_bibliotecario(request, reserva_id):
    with transaction.atomic():
        reserva = get_object_or_404(
            Reserva.objects.select_for_update().select_related('ejemplar_asignado', 'usuario', 'libro'),
            id=reserva_id
        )

        if reserva.estado not in ['PENDIENTE', 'DISPONIBLE']:
            messages.error(request, "Esta reserva ya no está activa.")
            return redirect('gestion_reservas')

        ejemplar = reserva.ejemplar_asignado
        ahora = timezone.now()

        reserva.estado = 'CANCELADA'
        reserva.ejemplar_asignado = None
        reserva.save(update_fields=['estado', 'ejemplar_asignado'])

        if ejemplar:
            ejemplar_bloqueado = Ejemplar.objects.select_for_update().select_related('libro').get(pk=ejemplar.pk)
            liberar_o_asignar_ejemplar(ejemplar_bloqueado, ahora)

        Notificacion.objects.create(
            usuario=reserva.usuario,
            tipo='GENERAL',
            mensaje=f"Tu reserva de \"{reserva.libro.titulo}\" fue cancelada en biblioteca.",
            leida=False,
            fecha=ahora
        )

    messages.success(request, f"Reserva #{reserva.id} de {reserva.usuario.username} cancelada.")
    return redirect('gestion_reservas')
