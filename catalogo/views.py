
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count, Prefetch
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

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
