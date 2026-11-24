from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Ejemplar, Libro
from cuentas.models import Usuario
from cuentas.permisos import bibliotecario_requerido, lector_requerido
from multas.models import Multa
from . import servicios
from .models import Prestamo, Reserva
from .servicios import ReglaNegocioError


# Solicita el préstamo de un libro (CU-06); delega reglas y transacción a prestamos/servicios.py
@lector_requerido
@require_POST
def solicitar_prestamo(request, libro_id):
    libro = get_object_or_404(Libro, id=libro_id, activo=True)

    try:
        prestamo = servicios.solicitar_prestamo(request.user.pk, libro)
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        # Si ya no quedan ejemplares disponibles, lleva al detalle para ofrecer reserva (CU-06 2a)
        if error.codigo == 'sin_disponibles':
            return redirect('detalle_libro', libro_id=libro.id)
        return redirect('lista_libros')

    # Muestra la confirmación en zona horaria local con código de inventario y plazo límite
    limite_local = timezone.localtime(prestamo.fecha_limite_recoger)
    messages.success(
        request,
        f"¡Solicitud exitosa! Acércate a recoger el ejemplar "
        f"[{prestamo.ejemplar.codigo_inventario}] antes de {limite_local:%d/%m/%Y %H:%M}.",
    )
    return redirect('mis_prestamos')


# Muestra los préstamos y reservas del usuario que inició sesión (CU-09, CU-13)
@lector_requerido
def mis_prestamos(request):
    usuario = request.user

    prestamos = Prestamo.objects.filter(
        usuario=usuario
    ).select_related(
        'ejemplar', 'ejemplar__libro'
    ).order_by('-fecha_solicitud')

    # Divide los préstamos del lector entre en curso y el historial paginado (RNF-05)
    estados_en_curso = ('SOLICITADO', 'ACTIVO', 'VENCIDO')
    en_curso = [p for p in prestamos if p.estado in estados_en_curso]
    historial_lista = [p for p in prestamos if p.estado not in estados_en_curso]
    historial = Paginator(historial_lista, 10).get_page(request.GET.get('page'))

    # Consulta las reservas activas del lector (en espera o ya disponibles para recoger)
    reservas_activas = Reserva.objects.filter(
        usuario=usuario,
        estado__in=['PENDIENTE', 'DISPONIBLE'],
    ).select_related(
        'libro', 'ejemplar_asignado'
    ).order_by('fecha_reserva', 'id')

    contexto = {
        'usuario': usuario,
        'titulo': 'Mis préstamos y reservas',
        'en_curso': en_curso,
        'historial': historial,
        'reservas_activas': reservas_activas,
    }
    return render(request, 'prestamos/mis_prestamos.html', contexto)


# Muestra las solicitudes por entregar y los libros prestados (CU-23, CU-24, CU-25)
@bibliotecario_requerido
def gestion_prestamos(request):
    busqueda = request.GET.get('q', '').strip()
    hoy = timezone.localdate()

    por_entregar = Prestamo.objects.filter(
        estado='SOLICITADO'
    ).select_related(
        'usuario', 'ejemplar', 'ejemplar__libro'
    ).order_by('fecha_solicitud')

    prestados_qs = Prestamo.objects.filter(
        estado__in=['ACTIVO', 'VENCIDO']
    ).select_related(
        'usuario', 'ejemplar', 'ejemplar__libro'
    ).order_by('fecha_vencimiento', 'id')

    codigos_prestados = list(
        prestados_qs.values_list(
            'ejemplar__codigo_inventario',
            'ejemplar__libro__titulo',
            'usuario__username',
        )
    )

    if busqueda:
        filtro = (
            Q(ejemplar__codigo_inventario__icontains=busqueda)
            | Q(usuario__username__icontains=busqueda)
            | Q(usuario__first_name__icontains=busqueda)
            | Q(usuario__last_name__icontains=busqueda)
            | Q(ejemplar__libro__titulo__icontains=busqueda)
        )
        por_entregar = por_entregar.filter(filtro)
        prestados_qs = prestados_qs.filter(filtro)

    prestados = Paginator(prestados_qs, 15).get_page(request.GET.get('page'))
    for p in prestados:
        p.retraso_actual = p.dias_retraso(hoy)

    multa_generada = None
    multa_id = request.GET.get('multa_id', '').strip()
    if multa_id.isdigit():
        multa_generada = Multa.objects.select_related(
            'usuario', 'prestamo__ejemplar__libro'
        ).filter(id=int(multa_id), estado='PENDIENTE').first()

    lectores = Usuario.objects.filter(
        tipo_usuario__in=['ESTUDIANTE', 'PROFESOR'],
        is_active=True,
        bloqueado=False,
    ).order_by('username')

    ejemplares_disponibles = Ejemplar.objects.filter(
        estado='DISPONIBLE',
        libro__activo=True,
    ).select_related('libro').order_by('codigo_inventario')

    contexto = {
        'usuario': request.user,
        'titulo': 'Gestión de préstamos',
        'por_entregar': por_entregar,
        'prestados': prestados,
        'busqueda': busqueda,
        'codigos_prestados': codigos_prestados,
        'multa_generada': multa_generada,
        'lectores': lectores,
        'ejemplares_disponibles': ejemplares_disponibles,
        'hoy': hoy,
    }
    return render(request, 'prestamos/gestion_prestamos.html', contexto)


# Entrega el libro al usuario: SOLICITADO -> ACTIVO (CU-23)
@bibliotecario_requerido
@require_POST
def entregar_prestamo(request, prestamo_id):
    try:
        prestamo, expirada = servicios.entregar_prestamo(prestamo_id, request.user)
    except Prestamo.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_prestamos')

    if expirada:
        messages.error(
            request,
            f"La solicitud #{prestamo.id} expiró porque venció su plazo para recoger (RN-06). "
            "El ejemplar fue liberado.",
        )
        return redirect('gestion_prestamos')

    messages.success(
        request,
        f"Libro entregado a {prestamo.usuario.username}. "
        f"Fecha de devolución: {prestamo.fecha_vencimiento:%d/%m/%Y}.",
    )
    return redirect('gestion_prestamos')


# Recibe el libro: ACTIVO/VENCIDO -> DEVUELTO (CU-25, CU-26)
@bibliotecario_requerido
@require_POST
def recibir_devolucion(request, prestamo_id):
    try:
        prestamo, multa, dias_retraso, reserva_asignada = servicios.recibir_devolucion(
            prestamo_id, request.user
        )
    except Prestamo.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_prestamos')

    if multa:
        messages.warning(
            request,
            f"Devolución registrada con {dias_retraso} día(s) de retraso. "
            f"Se generó una multa de ${multa.monto:.2f} para {prestamo.usuario.username}.",
        )
    else:
        messages.success(request, "Devolución registrada correctamente.")

    if reserva_asignada:
        messages.info(
            request,
            f"El ejemplar quedó apartado para {reserva_asignada.usuario.username} "
            f"(reserva #{reserva_asignada.id}).",
        )

    if multa:
        return redirect(f"{reverse('gestion_prestamos')}?multa_id={multa.id}")
    return redirect('gestion_prestamos')


# Registra un préstamo directo en mostrador sin solicitud previa: [*] -> ACTIVO (CU-24)
@bibliotecario_requerido
@require_POST
def registrar_prestamo_mostrador(request):
    username = request.POST.get('username', '').strip()
    codigo_inventario = request.POST.get('codigo_inventario', '').strip()
    observaciones = request.POST.get('observaciones', '').strip() or None

    if not username or not codigo_inventario:
        messages.error(
            request,
            "Debes indicar el usuario lector y el código de inventario del ejemplar.",
        )
        return redirect('gestion_prestamos')

    try:
        prestamo = servicios.registrar_prestamo_mostrador(
            username, codigo_inventario, request.user, observaciones=observaciones
        )
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_prestamos')

    messages.success(
        request,
        f"Préstamo en mostrador registrado: [{prestamo.ejemplar.codigo_inventario}] entregado a "
        f"{prestamo.usuario.username}. Devolver antes del {prestamo.fecha_vencimiento:%d/%m/%Y}.",
    )
    return redirect('gestion_prestamos')


# Registra pérdida o daño de un ejemplar prestado y genera multa de reposición (CU-27, RN-13)
@bibliotecario_requerido
@require_POST
def registrar_incidente_ejemplar(request, prestamo_id):
    motivo = request.POST.get('motivo', '').strip()
    observaciones = request.POST.get('observaciones', '').strip()

    try:
        (
            prestamo,
            multa_incidente,
            multa_retraso,
            dias_retraso,
            reservas_sin_ejemplar,
        ) = servicios.registrar_incidente_ejemplar(
            prestamo_id, motivo, request.user, observaciones=observaciones
        )
    except Prestamo.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_prestamos')

    etiqueta = 'daño' if motivo == 'DANIO' else 'pérdida'
    aviso_extra = (
        f" También se generó multa de ${multa_retraso.monto:.2f} "
        f"por {dias_retraso} día(s) de retraso."
        if multa_retraso
        else ""
    )
    messages.warning(
        request,
        f"Se registró {etiqueta} del ejemplar [{prestamo.ejemplar.codigo_inventario}]. "
        f"Multa por costo de reposición: ${multa_incidente.monto:.2f} "
        f"para {prestamo.usuario.username}.{aviso_extra}",
    )
    if reservas_sin_ejemplar:
        messages.info(
            request,
            f"Aviso: «{prestamo.ejemplar.libro.titulo}» tiene reservas pendientes "
            "pero ya no cuenta con ejemplares en circulación.",
        )
    return redirect('gestion_prestamos')
