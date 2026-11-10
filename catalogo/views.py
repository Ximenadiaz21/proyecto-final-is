
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count, Prefetch
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

from django.shortcuts import redirect
from django.contrib import messages
from django.db import transaction
from .forms import LibroForm, AutorForm, EditorialForm, CategoriaForm
from .models import LibroAutor

from .models import Libro, Categoria, LibroAutor, Ejemplar


# Prepara las relaciones de autores para no repetir consultas a MySQL
def obtener_libros():
    return Libro.objects.filter(
        activo=1
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

    libros = obtener_libros()

    # Busca coincidencias en los datos del libro y de sus autores
    if busqueda:
        libros = libros.filter(
            Q(titulo__icontains=busqueda) |
            Q(isbn__icontains=busqueda) |
            Q(editorial__nombre__icontains=busqueda) |
            Q(categoria__nombre__icontains=busqueda) |
            Q(libroautor__autor__nombre__icontains=busqueda) |
            Q(libroautor__autor__apellidos__icontains=busqueda)
        ).distinct()

    # Aplica el filtro de categoría cuando se selecciona una válida
    if categoria_id.isdigit():
        libros = libros.filter(categoria_id=int(categoria_id))

    # Ordena los resultados y muestra 12 libros por página
    libros = libros.order_by('titulo', 'id')
    paginador = Paginator(libros, 12)
    pagina = paginador.get_page(request.GET.get('page'))

    # Carga las categorías para mostrarlas en el buscador
    categorias = Categoria.objects.all().order_by('nombre')

    contexto = {
        'libros': pagina,
        'categorias': categorias,
        'busqueda': busqueda,
        'categoria_seleccionada': categoria_id,
        'pagina': pagina,
        'total_libros': paginador.count,
    }

    return render(request, 'catalogo/lista_libros.html', contexto)


# Muestra la información completa de un libro seleccionado
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

    contexto = {
        'libro': libro,
        'ejemplares': ejemplares,
    }

    return render(request, 'catalogo/detalle_libro.html', contexto)


from django.core.exceptions import PermissionDenied


# Permite que el bibliotecario consulte y administre los libros registrados
@login_required
def gestionar_libros(request):

    # Verifica que el usuario tenga permisos de bibliotecario
    if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
        raise PermissionDenied

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

    contexto = {
        'libros': pagina,
        'pagina': pagina,
        'busqueda': busqueda,
        'total_libros': paginador.count,
    }

    return render(request, 'catalogo/gestionar_libros.html', contexto)


# Permite al bibliotecario registrar un libro nuevo
@login_required
def nuevo_libro(request):

    # Solo los bibliotecarios activos pueden registrar libros
    if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
        raise PermissionDenied

    # Si se envía el formulario, comprueba y guarda sus datos
    if request.method == 'POST':
        formulario = LibroForm(request.POST)

        if formulario.is_valid():
            with transaction.atomic():

                # Guarda el libro como activo en MySQL
                libro = formulario.save(commit=False)
                libro.activo = 1
                libro.save()

                # Relaciona el libro con el autor seleccionado
                autor = formulario.cleaned_data['autor']

                LibroAutor.objects.create(
                    libro=libro,
                    autor=autor,
                    orden=1
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
@login_required
def nuevo_autor(request):

    # Comprueba que el usuario sea un bibliotecario activo
    if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
        raise PermissionDenied

    # Procesa los datos enviados por el bibliotecario
    if request.method == 'POST':
        formulario = AutorForm(request.POST)

        if formulario.is_valid():
            autor = formulario.save()

            messages.success(
                request,
                f'El autor {autor.nombre} {autor.apellidos} se registró correctamente.'
            )

            return redirect('nuevo_libro')

    else:
        formulario = AutorForm()

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Registrar nuevo autor',
        'descripcion_pagina': 'Agrega un autor para asociarlo a los libros de la biblioteca.',
    }

    return render(request, 'catalogo/formulario_autor.html', contexto)


# Permite al bibliotecario registrar nuevas editoriales
@login_required
def nueva_editorial(request):

    # Comprueba que el usuario sea un bibliotecario activo
    if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
        raise PermissionDenied

    # Guarda la editorial cuando el formulario es válido
    if request.method == 'POST':
        formulario = EditorialForm(request.POST)

        if formulario.is_valid():
            editorial = formulario.save()

            messages.success(
                request,
                f'La editorial {editorial.nombre} se registró correctamente.'
            )

            return redirect('nuevo_libro')

    else:
        formulario = EditorialForm()

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Registrar nueva editorial',
        'descripcion_pagina': 'Agrega una editorial para asociarla a los libros.',
        'titulo_seccion': 'Información de la editorial',
        'texto_boton': 'Guardar editorial',
    }

    return render(request, 'catalogo/formulario_dato.html', contexto)


# Permite al bibliotecario registrar nuevas categorías
@login_required
def nueva_categoria(request):

    # Comprueba que el usuario sea un bibliotecario activo
    if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
        raise PermissionDenied

    # Guarda la categoría cuando el formulario es válido
    if request.method == 'POST':
        formulario = CategoriaForm(request.POST)

        if formulario.is_valid():
            categoria = formulario.save()

            messages.success(
                request,
                f'La categoría {categoria.nombre} se registró correctamente.'
            )

            return redirect('nuevo_libro')

    else:
        formulario = CategoriaForm()

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Registrar nueva categoría',
        'descripcion_pagina': 'Agrega una categoría para organizar los libros.',
        'titulo_seccion': 'Información de la categoría',
        'texto_boton': 'Guardar categoría',
    }

    return render(request, 'catalogo/formulario_dato.html', contexto)


# Permite al bibliotecario modificar los datos de un libro existente
@login_required
def editar_libro(request, libro_id):

    # Comprueba que el usuario tenga permisos de bibliotecario
    if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
        raise PermissionDenied

    # Busca el libro que se desea editar
    libro = get_object_or_404(Libro, id=libro_id)

    if request.method == 'POST':
        formulario = LibroForm(request.POST, instance=libro)

        if formulario.is_valid():
            with transaction.atomic():

                # Actualiza los datos bibliográficos del libro
                libro = formulario.save()

                # Obtiene el autor seleccionado
                autor = formulario.cleaned_data['autor']

                # Actualiza la relación del autor principal
                relacion = LibroAutor.objects.filter(
                    libro=libro
                ).order_by('orden', 'id').first()

                if relacion:
                    relacion.autor = autor
                    relacion.save()
                else:
                    LibroAutor.objects.create(
                        libro=libro,
                        autor=autor,
                        orden=1
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
@login_required
def cambiar_estado_libro(request, libro_id):

    # Solo los bibliotecarios activos pueden modificar el catálogo
    if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
        raise PermissionDenied

    # Busca el libro que se desea modificar
    libro = get_object_or_404(Libro, id=libro_id)

    # El estado solamente puede cambiarse desde un formulario POST
    if request.method != 'POST':
        return redirect('gestionar_libros')

    # Cambia el estado actual del libro
    if libro.activo:
        libro.activo = 0
        mensaje = 'El libro fue dado de baja correctamente.'
    else:
        libro.activo = 1
        mensaje = 'El libro fue reactivado correctamente.'

    # Guarda únicamente el campo que cambió
    libro.save(update_fields=['activo'])

    messages.success(request, mensaje)

    return redirect('gestionar_libros')

