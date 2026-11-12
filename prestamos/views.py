from datetime import timedelta
from decimal import Decimal

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone

from catalogo.models import Libro, Ejemplar
from cuentas.models import Notificacion, Usuario
from .models import PoliticaPrestamo, Prestamo, Reserva
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


# Muestra los préstamos y reservas del usuario que inició sesión (CU-09, CU-13)
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

    # Obtiene las reservas activas del usuario (PENDIENTE o DISPONIBLE para recoger)
    reservas_activas = Reserva.objects.filter(
        usuario=usuario,
        estado__in=['PENDIENTE', 'DISPONIBLE']
    ).select_related(
        'libro', 'ejemplar_asignado'
    ).order_by('fecha_reserva')

    contexto = {
        'usuario': usuario,
        'titulo': 'Mis préstamos y reservas',
        'en_curso': en_curso,
        'historial': historial,
        'reservas_activas': reservas_activas,
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

    # Listas para facilitar el registro de préstamos directos en mostrador (CU-24)
    lectores = Usuario.objects.filter(
        tipo_usuario__in=['ESTUDIANTE', 'PROFESOR'],
        is_active=True,
        bloqueado=False
    ).order_by('username')

    ejemplares_disponibles = Ejemplar.objects.filter(
        estado='DISPONIBLE',
        libro__activo=True
    ).select_related('libro').order_by('codigo_inventario')

    contexto = {
        'usuario': request.user,
        'titulo': 'Gestión de préstamos',
        'por_entregar': por_entregar,
        'prestados': prestados,
        'lectores': lectores,
        'ejemplares_disponibles': ejemplares_disponibles,
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


# Registra un préstamo directo en mostrador sin solicitud previa: [*] -> ACTIVO (CU-24)
@login_required
@require_POST
def registrar_prestamo_mostrador(request):
    if not es_bibliotecario(request.user):
        messages.error(request, "No tienes permiso para registrar préstamos en mostrador.")
        return redirect('panel')

    username = request.POST.get('username', '').strip()
    codigo_inventario = request.POST.get('codigo_inventario', '').strip()
    observaciones = request.POST.get('observaciones', '').strip() or None

    if not username or not codigo_inventario:
        messages.error(request, "Debes indicar el usuario lector y el código de inventario del ejemplar.")
        return redirect('gestion_prestamos')

    # 1. Busca al usuario lector activo
    lector = Usuario.objects.filter(username=username, is_active=True).first()
    if not lector:
        messages.error(request, f"No se encontró un usuario activo con username «{username}».")
        return redirect('gestion_prestamos')

    if lector.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Solo se pueden prestar libros a estudiantes y profesores.")
        return redirect('gestion_prestamos')

    # 2. Verifica elegibilidad del usuario (CU-07, RN-08)
    motivo = motivo_inelegible(lector)
    if motivo:
        messages.error(request, f"No se puede prestar a {lector.username}: {motivo}")
        return redirect('gestion_prestamos')

    # 3. Obtiene la política según el tipo de usuario (RN-01, RN-02)
    try:
        politica = PoliticaPrestamo.objects.get(tipo_usuario=lector.tipo_usuario)
    except PoliticaPrestamo.DoesNotExist:
        messages.error(request, "No hay política de préstamo configurada para este tipo de usuario.")
        return redirect('gestion_prestamos')

    # 4. Verifica límite de libros simultáneos (RN-02)
    prestamos_activos = Prestamo.objects.filter(
        usuario=lector,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).count()

    if prestamos_activos >= politica.max_libros:
        messages.error(
            request,
            f"El usuario {lector.username} alcanzó su límite de libros permitidos ({politica.max_libros}) (RN-02)."
        )
        return redirect('gestion_prestamos')

    # 5. Transacción atómica para bloquear el ejemplar y crear el préstamo (RNF-03)
    with transaction.atomic():
        ejemplar = Ejemplar.objects.select_for_update().select_related('libro').filter(
            codigo_inventario=codigo_inventario
        ).first()

        if not ejemplar or not ejemplar.libro.activo:
            messages.error(request, f"No existe un ejemplar activo con código «{codigo_inventario}».")
            return redirect('gestion_prestamos')

        # RN-15: Solo se puede prestar en mostrador un ejemplar DISPONIBLE
        if ejemplar.estado != 'DISPONIBLE':
            messages.error(
                request,
                f"El ejemplar [{ejemplar.codigo_inventario}] no está disponible (estado actual: {ejemplar.estado}) (RN-15)."
            )
            return redirect('gestion_prestamos')

        # RN-11: Un usuario no puede tener dos préstamos activos del mismo título
        if Prestamo.objects.filter(
            usuario=lector,
            ejemplar__libro=ejemplar.libro,
            estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
        ).exists():
            messages.error(
                request,
                f"El usuario {lector.username} ya tiene un préstamo activo o solicitado de «{ejemplar.libro.titulo}» (RN-11)."
            )
            return redirect('gestion_prestamos')

        ahora = timezone.now()
        vencimiento = timezone.localdate() + timedelta(days=politica.dias_prestamo)

        prestamo = Prestamo.objects.create(
            usuario=lector,
            ejemplar=ejemplar,
            estado='ACTIVO',
            fecha_solicitud=ahora,
            fecha_prestamo=ahora,
            fecha_vencimiento=vencimiento,
            num_renovaciones=0,
            entregado_por=request.user,
            observaciones=observaciones
        )

        ejemplar.estado = 'PRESTADO'
        ejemplar.save(update_fields=['estado'])

        Notificacion.objects.create(
            usuario=lector,
            tipo='GENERAL',
            mensaje=(
                f"Préstamo #{prestamo.id} de \"{ejemplar.libro.titulo}\" ({ejemplar.codigo_inventario}) "
                f"registrado en mostrador. Fecha de devolución: {vencimiento.strftime('%d/%m/%Y')}."
            ),
            leida=False,
            fecha=ahora
        )

    messages.success(
        request,
        f"Préstamo en mostrador registrado: [{ejemplar.codigo_inventario}] entregado a {lector.username}. "
        f"Devolver antes del {vencimiento.strftime('%d/%m/%Y')}."
    )
    return redirect('gestion_prestamos')


# Registra la pérdida o el daño de un ejemplar prestado y genera la multa de reposición (CU-27, RN-13)
@login_required
@require_POST
def registrar_incidente_ejemplar(request, prestamo_id):
    if not es_bibliotecario(request.user):
        messages.error(request, "No tienes permiso para registrar incidentes de ejemplares.")
        return redirect('panel')

    motivo = request.POST.get('motivo', '').strip()
    observaciones = request.POST.get('observaciones', '').strip()

    if motivo not in ['DANIO', 'PERDIDA']:
        messages.error(request, "Debes indicar si el incidente es por daño o por pérdida.")
        return redirect('gestion_prestamos')

    multa_retraso = None

    with transaction.atomic():
        prestamo = get_object_or_404(
            Prestamo.objects.select_for_update().select_related('ejemplar', 'ejemplar__libro', 'usuario'),
            id=prestamo_id
        )

        if prestamo.estado not in ['ACTIVO', 'VENCIDO']:
            messages.error(request, "Este préstamo ya no está activo.")
            return redirect('gestion_prestamos')

        ahora = timezone.now()
        hoy = timezone.localdate()
        libro = prestamo.ejemplar.libro

        # RN-13: El monto de la multa por pérdida o daño es el costo de reposición del libro
        monto_reposicion = libro.costo_reposicion if libro.costo_reposicion > Decimal('0') else Decimal('150.00')

        # Si además se reporta después de la fecha de vencimiento, calcula la multa por retraso (RN-07)
        dias_retraso = prestamo.dias_retraso(hoy)
        if dias_retraso > 0:
            try:
                politica = PoliticaPrestamo.objects.get(tipo_usuario=prestamo.usuario.tipo_usuario)
                monto_retraso = prestamo.calcular_multa(politica, hoy)
                if monto_retraso > 0:
                    multa_retraso = Multa.objects.create(
                        prestamo=prestamo,
                        usuario=prestamo.usuario,
                        motivo='RETRASO',
                        dias_retraso=dias_retraso,
                        monto=monto_retraso,
                        estado='PENDIENTE',
                        fecha_generacion=ahora
                    )
            except PoliticaPrestamo.DoesNotExist:
                pass

        # Crea la multa adicional por daño o pérdida (RN-13)
        multa_incidente = Multa.objects.create(
            prestamo=prestamo,
            usuario=prestamo.usuario,
            motivo=motivo,
            dias_retraso=0,
            monto=monto_reposicion,
            estado='PENDIENTE',
            fecha_generacion=ahora
        )

        # Actualiza el estado del préstamo y del ejemplar según el diagrama de estados (Sección 10.3)
        if motivo == 'DANIO':
            prestamo.estado = 'DEVUELTO'
            prestamo.ejemplar.estado = 'EN_REPARACION'
            etiqueta_incidente = 'daño'
        else:
            prestamo.estado = 'PERDIDO'
            prestamo.ejemplar.estado = 'PERDIDO'
            etiqueta_incidente = 'pérdida'

        prestamo.fecha_devolucion = ahora
        prestamo.recibido_por = request.user
        if observaciones:
            prestamo.observaciones = observaciones[:255]
            prestamo.ejemplar.observaciones = observaciones[:255]
        prestamo.save()
        prestamo.ejemplar.save()

        # Notifica al usuario lector sobre el cargo de reposición
        Notificacion.objects.create(
            usuario=prestamo.usuario,
            tipo='MULTA',
            mensaje=(
                f"Se registró una multa de ${multa_incidente.monto:.2f} por {etiqueta_incidente} "
                f"del ejemplar [{prestamo.ejemplar.codigo_inventario}] de \"{libro.titulo}\" (RN-13)."
            ),
            leida=False,
            fecha=ahora
        )

    aviso_extra = (
        f" También se generó multa de ${multa_retraso.monto:.2f} por {dias_retraso} día(s) de retraso."
        if multa_retraso else ""
    )
    messages.warning(
        request,
        f"Se registró {etiqueta_incidente} del ejemplar [{prestamo.ejemplar.codigo_inventario}]. "
        f"Multa por costo de reposición: ${multa_incidente.monto:.2f} para {prestamo.usuario.username}.{aviso_extra}"
    )
    return redirect('gestion_prestamos')