from datetime import timedelta

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone

from catalogo.models import Libro, Ejemplar
from .models import PoliticaPrestamo, Prestamo
from multas.models import Multa


# Solicita el préstamo de un libro (CU-06)
@login_required
def solicitar_prestamo(request, libro_id):
    libro = get_object_or_404(Libro, id=libro_id, activo=1)
    usuario = request.user

    # 1. Solo estudiantes y profesores pueden pedir libros
    if usuario.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Los bibliotecarios no pueden solicitar préstamos.")
        return redirect('lista_libros')

    # 2. Revisa bloqueo, multas pendientes y préstamos vencidos (RN-08)
    if usuario.bloqueado:
        messages.error(request, "Tu cuenta está bloqueada. No puedes solicitar préstamos.")
        return redirect('lista_libros')

    tiene_multas = Multa.objects.filter(usuario=usuario, estado='PENDIENTE').exists()
    prestamos_vencidos = Prestamo.objects.filter(usuario=usuario, estado='VENCIDO').exists()

    if tiene_multas or prestamos_vencidos:
        messages.error(request, "No puedes solicitar libros porque tienes multas pendientes o préstamos vencidos (RN-08).")
        return redirect('lista_libros')

    # 3. Obtiene la política según el tipo de usuario
    try:
        politica = PoliticaPrestamo.objects.get(tipo_usuario=usuario.tipo_usuario)
    except PoliticaPrestamo.DoesNotExist:
        messages.error(request, "No hay una política de préstamo configurada para tu tipo de usuario.")
        return redirect('lista_libros')

    # 4. Valida el límite de libros simultáneos (RN-02)
    prestamos_activos = Prestamo.objects.filter(
        usuario=usuario,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).count()

    if prestamos_activos >= politica.max_libros:
        messages.error(request, f"Has alcanzado el límite máximo de libros permitidos ({politica.max_libros}).")
        return redirect('lista_libros')

    # 5. Evita repetir el mismo título (RN-11)
    mismo_titulo_activo = Prestamo.objects.filter(
        usuario=usuario,
        ejemplar__libro=libro,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).exists()

    if mismo_titulo_activo:
        messages.error(request, "Ya tienes un préstamo activo o solicitado de este mismo título (RN-11).")
        return redirect('lista_libros')

    # 6. Transacción atómica para apartar el ejemplar (RNF-03)
    with transaction.atomic():
        ejemplar_disponible = Ejemplar.objects.select_for_update().filter(
            libro=libro,
            estado='DISPONIBLE'
        ).first()

        if not ejemplar_disponible:
            messages.error(request, "Lo sentimos, ya no quedan ejemplares disponibles de este libro.")
            return redirect('lista_libros')

        ejemplar_disponible.estado = 'RESERVADO'
        ejemplar_disponible.save()

        # Fecha límite para recoger (RN-06)
        ahora = timezone.now()
        limite_recoger = ahora + timedelta(hours=politica.horas_para_recoger)

        Prestamo.objects.create(
            usuario=usuario,
            ejemplar=ejemplar_disponible,
            estado='SOLICITADO',
            fecha_solicitud=ahora,
            fecha_limite_recoger=limite_recoger,
            num_renovaciones=0
        )

        limite_local = timezone.localtime(limite_recoger)
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

    # Solo estudiantes y profesores tienen préstamos propios
    if usuario.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Esta sección es solo para estudiantes y profesores.")
        return redirect('panel')

    prestamos = Prestamo.objects.filter(
        usuario=usuario
    ).select_related(
        'ejemplar', 'ejemplar__libro'
    ).order_by('-fecha_solicitud')

    # Separa los préstamos en curso del historial
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


# Revisa que el usuario sea bibliotecario
def es_bibliotecario(usuario):
    return usuario.tipo_usuario == 'BIBLIOTECARIO'


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


# Entrega el libro al usuario: SOLICITADO -> ACTIVO
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

        # Toma los días de préstamo según el tipo de usuario
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


# Recibe el libro de vuelta: ACTIVO/VENCIDO -> DEVUELTO
@login_required
@require_POST
def recibir_devolucion(request, prestamo_id):
    if not es_bibliotecario(request.user):
        messages.error(request, "No tienes permiso para recibir devoluciones.")
        return redirect('panel')

    with transaction.atomic():
        prestamo = get_object_or_404(
            Prestamo.objects.select_for_update().select_related('ejemplar', 'usuario'),
            id=prestamo_id
        )

        if prestamo.estado not in ['ACTIVO', 'VENCIDO']:
            messages.error(request, "Este préstamo no está pendiente de devolución.")
            return redirect('gestion_prestamos')

        ahora = timezone.now()
        hoy = timezone.localdate()
        con_retraso = prestamo.fecha_vencimiento and prestamo.fecha_vencimiento < hoy

        prestamo.estado = 'DEVUELTO'
        prestamo.fecha_devolucion = ahora
        prestamo.recibido_por = request.user
        prestamo.save()

        prestamo.ejemplar.estado = 'DISPONIBLE'
        prestamo.ejemplar.save()

    if con_retraso:
        dias = (hoy - prestamo.fecha_vencimiento).days
        messages.warning(
            request,
            f"Devolución registrada con {dias} día(s) de retraso. "
            f"Falta generar la multa (pendiente de implementar)."
        )
    else:
        messages.success(request, "Devolución registrada correctamente.")

    return redirect('gestion_prestamos')