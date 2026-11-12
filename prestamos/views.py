from datetime import timedelta
from decimal import Decimal

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone

from catalogo.models import Libro, Ejemplar
from cuentas.models import Notificacion
from .models import PoliticaPrestamo, Prestamo
from .reglas import motivo_inelegible, liberar_o_asignar_ejemplar
from multas.models import Multa


# Solicita el préstamo de un libro (CU-06)
# Ahora solo acepta POST: el botón en lista_libros.html y detalle_libro.html
# debe ser un <form method="post"> con {% csrf_token %}.
@login_required
@require_POST
def solicitar_prestamo(request, libro_id):
    libro = get_object_or_404(Libro, id=libro_id, activo=1)
    usuario = request.user

    # 1. Solo estudiantes y profesores pueden pedir libros
    if usuario.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Los bibliotecarios no pueden solicitar préstamos.")
        return redirect('lista_libros')

    # 2. Elegibilidad: bloqueo, multas pendientes, préstamos vencidos (CU-07, RN-08)
    motivo = motivo_inelegible(usuario)
    if motivo:
        messages.error(request, motivo)
        return redirect('lista_libros')

    # 3. Política según el tipo de usuario
    try:
        politica = PoliticaPrestamo.objects.get(tipo_usuario=usuario.tipo_usuario)
    except PoliticaPrestamo.DoesNotExist:
        messages.error(request, "No hay una política de préstamo configurada para tu tipo de usuario.")
        return redirect('lista_libros')

    # 4. Límite de libros simultáneos (RN-02)
    prestamos_activos = Prestamo.objects.filter(
        usuario=usuario,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).count()

    if prestamos_activos >= politica.max_libros:
        messages.error(request, f"Has alcanzado el límite máximo de libros permitidos ({politica.max_libros}).")
        return redirect('lista_libros')

    # 5. Evita repetir el mismo título (RN-11)
    if Prestamo.objects.filter(
        usuario=usuario,
        ejemplar__libro=libro,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).exists():
        messages.error(request, "Ya tienes un préstamo activo o solicitado de este mismo título (RN-11).")
        return redirect('lista_libros')

    # 6. Transacción atómica para apartar el ejemplar (RNF-03)
    with transaction.atomic():
        ejemplar_disponible = Ejemplar.objects.select_for_update().filter(
            libro=libro,
            estado='DISPONIBLE'
        ).first()

        if not ejemplar_disponible:
            messages.error(request, "Ya no quedan ejemplares disponibles de este libro. Puedes reservarlo.")
            return redirect('detalle_libro', libro_id=libro.id)

        ejemplar_disponible.estado = 'RESERVADO'
        ejemplar_disponible.save()

        ahora = timezone.now()
        limite_recoger = ahora + timedelta(hours=politica.horas_para_recoger)
        limite_local = timezone.localtime(limite_recoger)

        prestamo = Prestamo.objects.create(
            usuario=usuario,
            ejemplar=ejemplar_disponible,
            estado='SOLICITADO',
            fecha_solicitud=ahora,
            fecha_limite_recoger=limite_recoger,
            num_renovaciones=0
        )

        # Postcondición de CU-06: notificación para el usuario
        Notificacion.objects.create(
            usuario=usuario,
            tipo='GENERAL',
            mensaje=(
                f"Solicitud #{prestamo.id} de \"{libro.titulo}\" registrada. "
                f"Recoge el ejemplar {ejemplar_disponible.codigo_inventario} antes del "
                f"{limite_local.strftime('%d/%m/%Y %H:%M')}."
            ),
            leida=0,
            fecha=ahora
        )

    messages.success(
        request,
        f"¡Solicitud exitosa! Acércate a recoger el ejemplar [{ejemplar_disponible.codigo_inventario}] "
        f"antes de {limite_local.strftime('%d/%m/%Y %H:%M')}."
    )
    return redirect('mis_prestamos')


# Muestra los préstamos del usuario que inició sesión
@login_required
def mis_prestamos(request):
    usuario = request.user

    if usuario.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Esta sección es solo para estudiantes y profesores.")
        return redirect('panel')

    prestamos = Prestamo.objects.filter(
        usuario=usuario
    ).select_related(
        'ejemplar', 'ejemplar__libro'
    ).order_by('-fecha_solicitud')

    estados_en_curso = ['SOLICITADO', 'ACTIVO', 'VENCIDO']
    en_curso = [p for p in prestamos if p.estado in estados_en_curso]
    historial = [p for p in prestamos if p.estado not in estados_en_curso]

    contexto = {
        'usuario': usuario,
        'titulo': 'Mis préstamos',
        'en_curso': en_curso,
        'historial': historial,
    }

    return render(request, 'prestamos/mis_prestamos.html', contexto)


# Revisa que el usuario sea bibliotecario y no esté bloqueado
def es_bibliotecario(usuario):
    return usuario.tipo_usuario == 'BIBLIOTECARIO' and not usuario.bloqueado


# Muestra las solicitudes por entregar y los libros prestados
@login_required
def gestion_prestamos(request):
    if not es_bibliotecario(request.user):
        messages.error(request, "Esta sección es solo para bibliotecarios.")
        return redirect('panel')

    por_entregar = Prestamo.objects.filter(
        estado='SOLICITADO'
    ).select_related(
        'usuario', 'ejemplar', 'ejemplar__libro'
    ).order_by('fecha_solicitud')

    prestados = Prestamo.objects.filter(
        estado__in=['ACTIVO', 'VENCIDO']
    ).select_related(
        'usuario', 'ejemplar', 'ejemplar__libro'
    ).order_by('fecha_vencimiento')

    contexto = {
        'usuario': request.user,
        'titulo': 'Gestión de préstamos',
        'por_entregar': por_entregar,
        'prestados': prestados,
        'hoy': timezone.localdate(),
    }

    return render(request, 'prestamos/gestion_prestamos.html', contexto)


# Entrega el libro al usuario: SOLICITADO -> ACTIVO (CU-23, incluye CU-07)
@login_required
@require_POST
def entregar_prestamo(request, prestamo_id):
    if not es_bibliotecario(request.user):
        messages.error(request, "No tienes permiso para entregar libros.")
        return redirect('panel')

    with transaction.atomic():
        prestamo = get_object_or_404(
            Prestamo.objects.select_for_update().select_related('ejemplar', 'usuario'),
            id=prestamo_id
        )

        if prestamo.estado != 'SOLICITADO':
            messages.error(request, "Este préstamo ya no está en estado solicitado.")
            return redirect('gestion_prestamos')

        # Re-verifica elegibilidad al momento de entregar (CU-23 <<include>> CU-07)
        motivo = motivo_inelegible(prestamo.usuario)
        if motivo:
            messages.error(request, f"No se puede entregar: {motivo}")
            return redirect('gestion_prestamos')

        try:
            politica = PoliticaPrestamo.objects.get(tipo_usuario=prestamo.usuario.tipo_usuario)
        except PoliticaPrestamo.DoesNotExist:
            messages.error(request, "No hay política de préstamo para este tipo de usuario.")
            return redirect('gestion_prestamos')

        ahora = timezone.now()

        prestamo.estado = 'ACTIVO'
        prestamo.fecha_prestamo = ahora
        prestamo.fecha_vencimiento = timezone.localdate() + timedelta(days=politica.dias_prestamo)
        prestamo.entregado_por = request.user
        prestamo.save()

        prestamo.ejemplar.estado = 'PRESTADO'
        prestamo.ejemplar.save()

    messages.success(
        request,
        f"Libro entregado a {prestamo.usuario.username}. "
        f"Fecha de devolución: {prestamo.fecha_vencimiento.strftime('%d/%m/%Y')}."
    )
    return redirect('gestion_prestamos')


# Recibe el libro: ACTIVO/VENCIDO -> DEVUELTO (multa si hay retraso, cola FIFO RN-12)
@login_required
@require_POST
def recibir_devolucion(request, prestamo_id):
    if not es_bibliotecario(request.user):
        messages.error(request, "No tienes permiso para recibir devoluciones.")
        return redirect('panel')

    multa = None
    dias_retraso = 0
    reserva_asignada = None

    with transaction.atomic():
        prestamo = get_object_or_404(
            Prestamo.objects.select_for_update().select_related('ejemplar', 'ejemplar__libro', 'usuario'),
            id=prestamo_id
        )

        if prestamo.estado not in ['ACTIVO', 'VENCIDO']:
            messages.error(request, "Este préstamo no está pendiente de devolución.")
            return redirect('gestion_prestamos')

        ahora = timezone.now()
        hoy = timezone.localdate()

        # Días de retraso (RN-07)
        if prestamo.fecha_vencimiento and prestamo.fecha_vencimiento < hoy:
            dias_retraso = (hoy - prestamo.fecha_vencimiento).days

        if dias_retraso > 0:
            try:
                politica = PoliticaPrestamo.objects.get(tipo_usuario=prestamo.usuario.tipo_usuario)
            except PoliticaPrestamo.DoesNotExist:
                messages.error(request, "No hay política de préstamo para calcular la multa. No se registró la devolución.")
                return redirect('gestion_prestamos')

            monto = min(Decimal(dias_retraso) * politica.multa_por_dia, politica.multa_maxima)

            if monto > 0:
                multa = Multa.objects.create(
                    prestamo=prestamo,
                    usuario=prestamo.usuario,
                    motivo='RETRASO',
                    dias_retraso=dias_retraso,
                    monto=monto,
                    estado='PENDIENTE',
                    fecha_generacion=ahora
                )

                Notificacion.objects.create(
                    usuario=prestamo.usuario,
                    tipo='MULTA',
                    mensaje=f"Se generó una multa de ${monto:.2f} por {dias_retraso} día(s) de retraso en la devolución de \"{prestamo.ejemplar.libro.titulo}\".",
                    leida=0,
                    fecha=ahora
                )

        prestamo.estado = 'DEVUELTO'
        prestamo.fecha_devolucion = ahora
        prestamo.recibido_por = request.user
        prestamo.save()

        # RN-12 / CU-25 flujo 6a: atiende la cola de reservas o deja DISPONIBLE
        reserva_asignada = liberar_o_asignar_ejemplar(prestamo.ejemplar, ahora)

    if multa:
        messages.warning(
            request,
            f"Devolución registrada con {dias_retraso} día(s) de retraso. "
            f"Se generó una multa de ${multa.monto:.2f} para {prestamo.usuario.username}."
        )
    else:
        messages.success(request, "Devolución registrada correctamente.")

    if reserva_asignada:
        messages.info(
            request,
            f"El ejemplar quedó apartado para {reserva_asignada.usuario.username} (reserva #{reserva_asignada.id})."
        )

    return redirect('gestion_prestamos')