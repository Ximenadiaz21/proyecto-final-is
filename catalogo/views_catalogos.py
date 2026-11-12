from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from cuentas.views_usuarios import bibliotecario_requerido
from .forms import AutorForm, CategoriaForm, EditorialForm
from .models import Autor, Categoria, Editorial


# Lista y permite administrar autores, editoriales y categorías (CU-19, RF-10)
@bibliotecario_requerido
def gestion_catalogos(request):
    # Obtiene el texto de búsqueda opcional
    busqueda = request.GET.get('q', '').strip()

    # 1. Consulta los autores con el conteo de libros asociados
    autores = Autor.objects.annotate(
        total_libros=Count('libroautor__libro', distinct=True)
    ).order_by('apellidos', 'nombre')

    # 2. Consulta las editoriales con el conteo de libros publicados
    editoriales = Editorial.objects.annotate(
        total_libros=Count('libro', distinct=True)
    ).order_by('nombre')

    # 3. Consulta las categorías con el conteo de libros clasificados
    categorias = Categoria.objects.annotate(
        total_libros=Count('libro', distinct=True)
    ).order_by('nombre')

    # Aplica el filtro de búsqueda en las tres listas si se ingresó un término
    if busqueda:
        autores = autores.filter(
            Q(nombre__icontains=busqueda) |
            Q(apellidos__icontains=busqueda) |
            Q(nacionalidad__icontains=busqueda)
        )
        editoriales = editoriales.filter(
            Q(nombre__icontains=busqueda) |
            Q(pais__icontains=busqueda)
        )
        categorias = categorias.filter(
            Q(nombre__icontains=busqueda) |
            Q(descripcion__icontains=busqueda)
        )

    contexto = {
        'usuario': request.user,
        'titulo': 'Autores, editoriales y categorías',
        'busqueda': busqueda,
        'autores': autores,
        'editoriales': editoriales,
        'categorias': categorias,
    }

    return render(request, 'catalogo/gestion_catalogos.html', contexto)


# Permite al bibliotecario editar los datos de un autor existente (CU-19, RF-10)
@bibliotecario_requerido
def editar_autor(request, autor_id):
    autor = get_object_or_404(Autor, id=autor_id)

    if request.method == 'POST':
        formulario = AutorForm(request.POST, instance=autor)
        if formulario.is_valid():
            guardado = formulario.save()
            messages.success(
                request,
                f"El autor {guardado.nombre} {guardado.apellidos} se actualizó correctamente."
            )
            return redirect('gestion_catalogos')
    else:
        formulario = AutorForm(instance=autor)

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Editar autor',
        'descripcion_pagina': 'Modifica el nombre, apellidos o nacionalidad del autor.',
        'url_cancelar': 'gestion_catalogos',
    }

    return render(request, 'catalogo/formulario_autor.html', contexto)


# Permite al bibliotecario editar los datos de una editorial existente (CU-19, RF-10)
@bibliotecario_requerido
def editar_editorial(request, editorial_id):
    editorial = get_object_or_404(Editorial, id=editorial_id)

    if request.method == 'POST':
        formulario = EditorialForm(request.POST, instance=editorial)
        if formulario.is_valid():
            guardada = formulario.save()
            messages.success(
                request,
                f"La editorial {guardada.nombre} se actualizó correctamente."
            )
            return redirect('gestion_catalogos')
    else:
        formulario = EditorialForm(instance=editorial)

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Editar editorial',
        'descripcion_pagina': 'Actualiza el nombre o país de la editorial.',
        'titulo_seccion': 'Información de la editorial',
        'texto_boton': 'Guardar cambios',
        'url_cancelar': 'gestion_catalogos',
    }

    return render(request, 'catalogo/formulario_dato.html', contexto)


# Permite al bibliotecario editar los datos de una categoría existente (CU-19, RF-10)
@bibliotecario_requerido
def editar_categoria(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id)

    if request.method == 'POST':
        formulario = CategoriaForm(request.POST, instance=categoria)
        if formulario.is_valid():
            guardada = formulario.save()
            messages.success(
                request,
                f"La categoría {guardada.nombre} se actualizó correctamente."
            )
            return redirect('gestion_catalogos')
    else:
        formulario = CategoriaForm(instance=categoria)

    contexto = {
        'formulario': formulario,
        'titulo_pagina': 'Editar categoría',
        'descripcion_pagina': 'Actualiza el nombre o la descripción de la categoría.',
        'titulo_seccion': 'Información de la categoría',
        'texto_boton': 'Guardar cambios',
        'url_cancelar': 'gestion_catalogos',
    }

    return render(request, 'catalogo/formulario_dato.html', contexto)
