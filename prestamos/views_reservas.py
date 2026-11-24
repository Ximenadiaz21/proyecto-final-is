from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalogo.models import Libro
from cuentas.permisos import bibliotecario_requerido, lector_requerido
from . import servicios
from .models import Reserva
from .servicios import ReglaNegocioError


# Permite a un estudiante o profesor reservar un libro sin ejemplares disponibles (CU-11)
@lector_requerido
@require_POST
def reservar_libro(request, libro_id):
    libro = get_object_or_404(Libro, id=libro_id, activo=True)

    try:
        _, posicion = servicios.reservar_libro(request.user.pk, libro)
    except ReglaNegocioError as error:
        # Si mientras tanto se liberó una copia, invita al lector a solicitar préstamo directo
        if error.codigo == 'hay_disponibles':
            messages.info(request, str(error))
            return redirect('detalle_libro', libro_id=libro.id)
        messages.error(request, str(error))
        # Si ya tenía reserva activa de este título, lo lleva a Mis préstamos y reservas
        if error.codigo == 'ya_reservado':
            return redirect('mis_prestamos')
        return redirect('detalle_libro', libro_id=libro.id)

    messages.success(
        request,
        f"¡Reserva registrada para \"{libro.titulo}\"! Tu lugar en la cola de espera es el #{posicion}.",
    )
    return redirect('mis_prestamos')


# Permite al usuario lector cancelar su propia reserva (CU-12)
@lector_requerido
@require_POST
def cancelar_reserva(request, reserva_id):
    try:
        servicios.cancelar_reserva(reserva_id, usuario=request.user, por_bibliotecario=False)
    except Reserva.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('mis_prestamos')

    messages.success(request, "Tu reserva ha sido cancelada correctamente.")
    return redirect('mis_prestamos')


# Panel del bibliotecario para consultar y atender las reservas (CU-30)
@bibliotecario_requerido
def gestion_reservas(request):
    disponibles = Reserva.objects.filter(
        estado='DISPONIBLE'
    ).select_related(
        'usuario', 'libro', 'ejemplar_asignado'
    ).order_by('fecha_expiracion')

    pendientes = Reserva.objects.filter(
        estado='PENDIENTE'
    ).select_related(
        'usuario', 'libro'
    ).order_by('fecha_reserva', 'id')

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


# Entrega el ejemplar apartado de una reserva DISPONIBLE y crea el préstamo ACTIVO (CU-30)
@bibliotecario_requerido
@require_POST
def atender_reserva(request, reserva_id):
    try:
        prestamo, reserva, expirada = servicios.atender_reserva(reserva_id, request.user)
    except Reserva.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_reservas')

    if expirada:
        messages.error(
            request,
            f"La reserva #{reserva.id} expiró porque venció su plazo para recoger (RN-06). "
            "El ejemplar fue liberado o asignado al siguiente usuario en cola.",
        )
        return redirect('gestion_reservas')

    messages.success(
        request,
        f"Reserva atendida: ejemplar [{prestamo.ejemplar.codigo_inventario}] entregado a "
        f"{prestamo.usuario.username}. Fecha de devolución: {prestamo.fecha_vencimiento:%d/%m/%Y}.",
    )
    return redirect('gestion_reservas')


# Permite al bibliotecario cancelar una reserva activa y liberar/reasignar su ejemplar (CU-30)
@bibliotecario_requerido
@require_POST
def cancelar_reserva_bibliotecario(request, reserva_id):
    try:
        reserva, _ = servicios.cancelar_reserva(reserva_id, por_bibliotecario=True)
    except Reserva.DoesNotExist:
        raise Http404
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return redirect('gestion_reservas')

    messages.success(request, f"Reserva #{reserva.id} de {reserva.usuario.username} cancelada.")
    return redirect('gestion_reservas')
