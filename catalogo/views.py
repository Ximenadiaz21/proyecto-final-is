
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.permisos import bibliotecario_requerido
from prestamos.models import PoliticaPrestamo, Prestamo, Reserva
from prestamos.reglas import libros_en_uso, motivo_inelegible
from .forms import AutorForm, CategoriaForm, EditorialForm, LibroForm
from .models import Categoria, Ejemplar, Libro, LibroAutor


# Prepara las relaciones de autores para no repetir consultas a MySQL
def obtener_libros():
    return Libro.objects.filter(
        activo=True
    ).select_related(
        'categoria', 'editorial'
    ).prefetch_related(
        Prefetch(
            'libroautor_set',
            queryset=LibroAutor.objects.select_related('autor').order_by('orden')
        )
    ).annotate(
        disponibles=Count(
            'ejemplar',
            filter=Q(ejemplar__estado='DISPONIBLE'),
            distinct=True
        )
    )


# Muestra los libros del catálogo y permite buscarlos o filtrarlos
@login_required
def lista_libros(request):

    # Obtiene los valores escritos en el formulario
    busqueda = request.GET.get('q', '').strip()
    categoria_id = request.GET.get('categoria', '')
    solo_disponibles = request.GET.get('disponibles') == '1'

    libros = obtener_libros()

    # Busca coincidencias en los datos del libro y de sus autores (acepta ISBN con guiones)
    if busqueda:
        isbn_limpio = busqueda.replace('-', '').replace(' ', '')
        libros = libros.filter(
            Q(titulo__icontains=busqueda) |
            Q(subtitulo__icontains=busqueda) |
            Q(isbn__icontains=isbn_limpio) |
            Q(editorial__nombre__icontains=busqueda) |
            Q(categoria__nombre__icontains=busqueda) |
            Q(libroautor__autor__nombre__icontains=busqueda) |
            Q(libroautor__autor__apellidos__icontains=busqueda)
        ).distinct()

    # Aplica el filtro de categoría cuando se selecciona una válida
    if categoria_id.isdigit():
        libros = libros.filter(categoria_id=int(categoria_id))

    # Filtra únicamente libros con al menos un ejemplar disponible si se marcó la casilla
    if solo_disponibles:
        libros = libros.filter(disponibles__gt=0)

    # Ordena los resultados y muestra 12 libros por página
    libros = libros.order_by('titulo', 'id')
    paginador = Paginator(libros, 12)
    pagina = paginador.get_page(request.GET.get('page'))
    rango_paginas = list(paginador.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1))

    # Carga las categorías para mostrarlas en el buscador
    categorias = Categoria.objects.all().order_by('nombre')

    contexto = {
        'libros': pagina,
        'categorias': categorias,
        'busqueda': busqueda,
        'categoria_seleccionada': categoria_id,
        'solo_disponibles': solo_disponibles,
        'pagina': pagina,
        'rango_paginas': rango_paginas,
        'ellipsis': paginador.ELLIPSIS,
        'total_libros': paginador.count,
    }

    return render(request, 'catalogo/lista_libros.html', contexto)


# Muestra la información completa de un libro seleccionado (CU-05)
@login_required
def detalle_libro(request, libro_id):
    # Busca el libro solicitado y devuelve 404 si no existe
    libro = get_object_or_404(
        obtener_libros(),
        id=libro_id
    )

    # Consulta los ejemplares físicos y su estado actual
    ejemplares = Ejemplar.objects.filter(
        libro=libro
    ).order_by('codigo_inventario')

    # Evalúa elegibilidad (CU-06 paso 4 <<include>> CU-07) y política antes de mostrar el resumen (paso 5)
    politica = None
    fecha_vencimiento_estimada = None
    limite_recoger_estimado = None
    motivo_no_puede_solicitar = ''
    motivo_no_puede_reservar = ''

    if request.user.tipo_usuario in ('ESTUDIANTE', 'PROFESOR'):
        politica = PoliticaPrestamo.objects.filter(
            tipo_usuario=request.user.tipo_usuario
        ).first()
        if politica:
            fecha_vencimiento_estimada = timezone.localdate() + timedelta(days=politica.dias_prestamo)
            limite_recoger_estimado = timezone.now() + timedelta(hours=politica.horas_para_recoger)

        motivo_general = motivo_inelegible(request.user)
        tiene_mismo_titulo = Prestamo.objects.filter(
            usuario=request.user,
            ejemplar__libro=libro,
            estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO'],
        ).exists()

        if motivo_general:
            motivo_no_puede_solicitar = motivo_general
            motivo_no_puede_reservar = motivo_general
        elif tiene_mismo_titulo:
            msg_titulo = "Ya tienes un préstamo activo o solicitado de este mismo título (RN-11)."
            motivo_no_puede_solicitar = msg_titulo
            motivo_no_puede_reservar = msg_titulo
        elif politica and libros_en_uso(request.user) >= politica.max_libros:
            motivo_no_puede_solicitar = (
                f"Has alcanzado el límite máximo de libros permitidos ({politica.max_libros}) (RN-02)."
            )

        if not motivo_no_puede_reservar:
            if Reserva.objects.filter(
                usuario=request.user,
                libro=libro,
                estado__in=['PENDIENTE', 'DISPONIBLE'],
            ).exists():
                motivo_no_puede_reservar = "Ya tienes una reserva activa para este libro."

    contexto = {
        'libro': libro,
        'ejemplares': ejemplares,
        'politica': politica,
        'fecha_vencimiento_estimada': fecha_vencimiento_estimada,
        'limite_recoger_estimado': limite_recoger_estimado,
        'motivo_no_puede_solicitar': motivo_no_puede_solicitar,
        'motivo_no_puede_reservar': motivo_no_puede_reservar,
    }

    return render(request, 'catalogo/detalle_libro.html', contexto)


# Permite que el bibliotecario consulte y administre los libros registrados
@bibliotecario_requerido
def gestionar_libros(request):
    # Obtiene los libros, sus categorías, editoriales y autores
    libros = Libro.objects.select_related(
        'categoria', 'editorial'
    ).prefetch_related(
        Prefetch(
            'libroautor_set',
            queryset=LibroAutor.objects.select_related('autor')
        )
    ).annotate(
        total_ejemplares=Count('ejemplar', distinct=True),
        disponibles=Count(
            'ejemplar',
            filter=Q(ejemplar__estado='DISPONIBLE'),
            distinct=True
        )
    )

    # Permite buscar por título, autor o ISBN
    busqueda = request.GET.get('q', '').strip()

    if busqueda:
        libros = libros.filter(
            Q(titulo__icontains=busqueda) |
            Q(isbn__icontains=busqueda) |
            Q(libroautor__autor__nombre__icontains=busqueda) |
            Q(libroautor__autor__apellidos__icontains=busqueda)
        ).distinct()

    # Ordena los libros y divide los resultados en páginas
    libros = libros.order_by('titulo', 'id')
    paginador = Paginator(libros, 15)
    pagina = paginador.get_page(request.GET.get('page'))
    rango_paginas = list(paginador.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1))

    contexto = {
        'libros': pagina,
        'pagina': pagina,
        'rango_paginas': rango_paginas,
        'ellipsis': paginador.ELLIPSIS,
        'busqueda': busqueda,
        'total_libros': paginador.count,
    }

    return render(request, 'catalogo/gestionar_libros.html', contexto)


# Sincroniza autor principal y coautores de un libro respetando el orden en libro_autor
def _guardar_autores_libro(libro, autor_principal, coautores):
    autores_ordenados = [autor_principal]
    for coautor in coautores:
        if coautor.pk != autor_principal.pk and all(a.pk != coautor.pk for a in autores_ordenados):
            autores_ordenados.append(coautor)

    LibroAutor.objects.filter(libro=libro).delete()
    for orden, autor in enumerate(autores_ordenados, start=1):
        LibroAutor.objects.create(libro=libro, autor=autor, orden=orden)


# Resuelve a qué pantalla regresar al crear autor, editorial o categoría
def _destino_catalogo(request):
    siguiente = request.POST.get('next') or request.GET.get('next') or 'nuevo_libro'
    if siguiente in ('gestion_catalogos', 'nuevo_libro'):
        return siguiente
    return 'nuevo_libro'


# Permite al bibliotecario registrar un libro nuevo
@bibliotecario_requerido
def nuevo_libro(request):
    # Si se envía el formulario, comprueba y guarda sus datos
    if request.method == 'POST':
        formulario = LibroForm(request.POST)

        if formulario.is_valid():
            with transaction.atomic():

                # Guarda el libro como activo en MySQL
                libro = formulario.save(commit=False)
                libro.activo = True
                libro.save()

                # Relaciona el libro con su autor principal y sus coautores
                _guardar_autores_libro(
                    libro,
                    formulario.cleaned_data['autor'],
                    formulario.cleaned_data.get('coautores', []),
                )

            messages.success(
                request,
                'El libro se registró correctamente.'
            )

            return redirect('gestionar_libros')

    else:
        # Muestra un formulario vacío al entrar por primera vez
        formulario = LibroForm()

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Registrar nuevo libro',
    }

    return render(request, 'catalogo/formulario_libro.html', contexto)



# Permite al bibliotecario registrar nuevos autores
@bibliotecario_requerido
def nuevo_autor(request):
    destino = _destino_catalogo(request)

    # Procesa los datos enviados por el bibliotecario
    if request.method == 'POST':
        formulario = AutorForm(request.POST)

        if formulario.is_valid():
            autor = formulario.save()

            messages.success(
                request,
                f'El autor {autor.nombre} {autor.apellidos} se registró correctamente.'
            )

            return redirect(destino)

    else:
        formulario = AutorForm()

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Registrar nuevo autor',
        'descripcion_pagina': 'Agrega un autor para asociarlo a los libros de la biblioteca.',
        'url_cancelar': destino,
    }

    return render(request, 'catalogo/formulario_autor.html', contexto)


# Permite al bibliotecario registrar nuevas editoriales
@bibliotecario_requerido
def nueva_editorial(request):
    destino = _destino_catalogo(request)

    # Guarda la editorial cuando el formulario es válido
    if request.method == 'POST':
        formulario = EditorialForm(request.POST)

        if formulario.is_valid():
            editorial = formulario.save()

            messages.success(
                request,
                f'La editorial {editorial.nombre} se registró correctamente.'
            )

            return redirect(destino)

    else:
        formulario = EditorialForm()

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Registrar nueva editorial',
        'descripcion_pagina': 'Agrega una editorial para asociarla a los libros.',
        'titulo_seccion': 'Información de la editorial',
        'texto_boton': 'Guardar editorial',
        'url_cancelar': destino,
    }

    return render(request, 'catalogo/formulario_dato.html', contexto)


# Permite al bibliotecario registrar nuevas categorías
@bibliotecario_requerido
def nueva_categoria(request):
    destino = _destino_catalogo(request)

    # Guarda la categoría cuando el formulario es válido
    if request.method == 'POST':
        formulario = CategoriaForm(request.POST)

        if formulario.is_valid():
            categoria = formulario.save()

            messages.success(
                request,
                f'La categoría {categoria.nombre} se registró correctamente.'
            )

            return redirect(destino)

    else:
        formulario = CategoriaForm()

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Registrar nueva categoría',
        'descripcion_pagina': 'Agrega una categoría para organizar los libros.',
        'titulo_seccion': 'Información de la categoría',
        'texto_boton': 'Guardar categoría',
        'url_cancelar': destino,
    }

    return render(request, 'catalogo/formulario_dato.html', contexto)


# Permite al bibliotecario modificar los datos de un libro existente
@bibliotecario_requerido
def editar_libro(request, libro_id):
    # Busca el libro que se desea editar
    libro = get_object_or_404(Libro, id=libro_id)

    if request.method == 'POST':
        formulario = LibroForm(request.POST, instance=libro)

        if formulario.is_valid():
            with transaction.atomic():

                # Actualiza los datos bibliográficos del libro
                libro = formulario.save()

                # Actualiza autor principal y coautores
                _guardar_autores_libro(
                    libro,
                    formulario.cleaned_data['autor'],
                    formulario.cleaned_data.get('coautores', []),
                )

            messages.success(
                request,
                'Los datos del libro se actualizaron correctamente.'
            )

            return redirect('gestionar_libros')

    else:
        # Carga los datos actuales para mostrarlos en el formulario
        formulario = LibroForm(instance=libro)

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Editar libro',
        'libro': libro,
    }

    return render(request, 'catalogo/formulario_libro.html', contexto)


# Permite dar de baja o reactivar un libro sin eliminarlo de MySQL
@bibliotecario_requerido
@require_POST
def cambiar_estado_libro(request, libro_id):
    with transaction.atomic():
        # Bloquea el registro del libro dentro de la transacción
        libro = get_object_or_404(Libro.objects.select_for_update(), id=libro_id)

        if libro.activo:
            # No permite dar de baja si hay préstamos en curso o reservas activas
            if Prestamo.objects.filter(
                ejemplar__libro=libro,
                estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO'],
            ).exists():
                messages.error(
                    request,
                    f"No se puede dar de baja «{libro.titulo}» porque tiene préstamos solicitados, activos o vencidos."
                )
                return redirect('gestionar_libros')

            if Reserva.objects.filter(
                libro=libro,
                estado__in=['PENDIENTE', 'DISPONIBLE'],
            ).exists():
                messages.error(
                    request,
                    f"No se puede dar de baja «{libro.titulo}» porque tiene reservas activas. "
                    "Cancélalas primero desde Gestión de reservas."
                )
                return redirect('gestionar_libros')

            libro.activo = False
            # Pasa los ejemplares disponibles a BAJA para mantener coherente el ciclo de vida
            Ejemplar.objects.filter(libro=libro, estado=Ejemplar.Estado.DISPONIBLE).update(
                estado=Ejemplar.Estado.BAJA
            )
            mensaje = 'El libro fue dado de baja correctamente.'
        else:
            libro.activo = True
            mensaje = 'El libro fue reactivado correctamente.'

        libro.save(update_fields=['activo'])

    messages.success(request, mensaje)
    return redirect('gestionar_libros')

