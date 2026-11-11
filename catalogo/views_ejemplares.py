from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from cuentas.views_usuarios import bibliotecario_requerido
from .forms_ejemplares import (
    EjemplarForm, ESTADOS, ESTADOS_MANUALES, estado_bloqueado,
)
from .models import Libro, Ejemplar


# Lista los ejemplares con buscador y filtros (CU-18)
@bibliotecario_requerido
def gestion_ejemplares(request):
    busqueda = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '')
    libro_id = request.GET.get('libro', '')

    ejemplares = Ejemplar.objects.select_related('libro').order_by('libro__titulo', 'codigo_inventario')

    if busqueda:
        ejemplares = ejemplares.filter(
            Q(codigo_inventario__icontains=busqueda) |
            Q(libro__titulo__icontains=busqueda) |
            Q(libro__isbn__icontains=busqueda) |
            Q(ubicacion__icontains=busqueda)
        )

    if estado in dict(ESTADOS):
        ejemplares = ejemplares.filter(estado=estado)

    libro_filtro = None
    if libro_id.isdigit():
        libro_filtro = Libro.objects.filter(pk=int(libro_id)).first()
        if libro_filtro:
            ejemplares = ejemplares.filter(libro=libro_filtro)

    pagina = Paginator(ejemplares, 20).get_page(request.GET.get('page'))

    # Resumen de ejemplares por estado
    conteo = {fila['estado']: fila['n'] for fila in
              Ejemplar.objects.values('estado').annotate(n=Count('id'))}
    resumen = [(valor, nombre, conteo.get(valor, 0)) for valor, nombre in ESTADOS]

    parametros = request.GET.copy()
    parametros.pop('page', None)

    contexto = {
        'usuario': request.user,
        'titulo': 'Gestión de ejemplares',
        'pagina': pagina,
        'busqueda': busqueda,
        'estado': estado,
        'estados': ESTADOS,
        'libro_filtro': libro_filtro,
        'resumen': resumen,
        'querystring': parametros.urlencode(),
        'siguiente': request.get_full_path(),
    }

    return render(request, 'ejemplares/gestion_ejemplares.html', contexto)


# Da de alta uno o varios ejemplares
@bibliotecario_requerido
def nuevo_ejemplar(request):
    libro_inicial = None
    libro_id = request.GET.get('libro', '')
    if libro_id.isdigit():
        libro_inicial = Libro.objects.filter(pk=int(libro_id)).first()

    datos = request.POST if request.method == 'POST' else None
    form = EjemplarForm(datos, libro_inicial=libro_inicial)

    if request.method == 'POST' and form.is_valid():
        creados = form.save()
        if len(creados) == 1:
            messages.success(request, f"Ejemplar {creados[0].codigo_inventario} creado correctamente.")
        else:
            messages.success(
                request,
                f"{len(creados)} ejemplares creados ({creados[0].codigo_inventario} a {creados[-1].codigo_inventario})."
            )
        return redirect(f"{reverse('gestion_ejemplares')}?libro={form.libro.pk}")

    contexto = {
        'usuario': request.user,
        'titulo': 'Nuevo ejemplar',
        'form': form,
        'editando': None,
    }
    return render(request, 'ejemplares/formulario_ejemplar.html', contexto)


# Edita un ejemplar existente
@bibliotecario_requerido
def editar_ejemplar(request, ejemplar_id):
    editando = get_object_or_404(Ejemplar.objects.select_related('libro'), id=ejemplar_id)
    datos = request.POST if request.method == 'POST' else None
    form = EjemplarForm(datos, instance=editando)

    if request.method == 'POST' and form.is_valid():
        guardado = form.save()[0]
        messages.success(request, f"Ejemplar {guardado.codigo_inventario} actualizado correctamente.")
        return redirect(f"{reverse('gestion_ejemplares')}?libro={guardado.libro_id}")

    contexto = {
        'usuario': request.user,
        'titulo': 'Editar ejemplar',
        'form': form,
        'editando': editando,
    }
    return render(request, 'ejemplares/formulario_ejemplar.html', contexto)


# Cambia el estado de un ejemplar: disponible, en reparación, perdido o baja
@bibliotecario_requerido
@require_POST
def cambiar_estado_ejemplar(request, ejemplar_id):
    nuevo = request.POST.get('estado', '')
    destino = request.POST.get('volver', '')

    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = reverse('gestion_ejemplares')

    if nuevo not in dict(ESTADOS_MANUALES):
        messages.error(request, "Estado no válido.")
        return redirect(destino)

    with transaction.atomic():
        ejemplar = get_object_or_404(Ejemplar.objects.select_for_update(), id=ejemplar_id)

        if estado_bloqueado(ejemplar):
            messages.error(
                request,
                f"El ejemplar {ejemplar.codigo_inventario} está ligado a un préstamo en curso; "
                "su estado lo controla el sistema."
            )
            return redirect(destino)

        ejemplar.estado = nuevo
        ejemplar.save(update_fields=['estado'])

    messages.success(request, f"Ejemplar {ejemplar.codigo_inventario}: estado cambiado a {nuevo}.")
    return redirect(destino)
