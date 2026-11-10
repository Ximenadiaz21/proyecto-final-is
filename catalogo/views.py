
from django.shortcuts import render
from django.db.models import Q, Count
from django.contrib.auth.decorators import login_required

from .models import Libro, Categoria


# Muestra el catálogo de libros
@login_required
def lista_libros(request):

    # Obtén el texto escrito en el buscador
    busqueda = request.GET.get('q', '').strip()
    categoria_id = request.GET.get('categoria', '')

    # Consulta los libros activos
    libros = Libro.objects.filter(
        activo=1
    ).select_related(
        'categoria', 'editorial'
    ).annotate(
        disponibles=Count(
            'ejemplar',
            filter=Q(ejemplar__estado='DISPONIBLE'),
            distinct=True
        )
    )

    # Busca libros por título, ISBN, autor o editorial
    if busqueda:
        libros = libros.filter(
            Q(titulo__icontains=busqueda) |
            Q(isbn__icontains=busqueda) |
            Q(editorial__nombre__icontains=busqueda) |
            Q(categoria__nombre__icontains=busqueda) |
            Q(libroautor__autor__nombre__icontains=busqueda) |
            Q(libroautor__autor__apellidos__icontains=busqueda)
        ).distinct()

    # Filtra los libros por categoría
    if categoria_id.isdigit():
        libros = libros.filter(categoria_id=int(categoria_id))

    # Ordena los libros alfabéticamente
    libros = libros.order_by('titulo', 'id')

    # Obtén las categorías
    categorias = Categoria.objects.all().order_by('nombre')

    # Envía los datos al HTML
    contexto = {
        'libros': libros,
        'categorias': categorias,
        'busqueda': busqueda,
        'categoria_seleccionada': categoria_id,
    }

    # Abre la página del catálogo
    return render(request, 'catalogo/lista_libros.html', contexto)
