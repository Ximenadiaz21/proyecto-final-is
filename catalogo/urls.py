
from django.urls import path
from . import views
from . import views_catalogos

urlpatterns = [
    # Muestra el catálogo de libros
    path('', views.lista_libros, name='lista_libros'),

    # Muestra la información detallada de un libro
    path('<int:libro_id>/', views.detalle_libro, name='detalle_libro'),

    # Administración del catálogo
    path('gestion/', views.gestionar_libros, name='gestionar_libros'),

    # Gestión de autores, editoriales y categorías (CU-19, RF-10)
    path('gestion/catalogos/', views_catalogos.gestion_catalogos, name='gestion_catalogos'),

    # Formulario para registrar nuevos libros
    path('gestion/nuevo/', views.nuevo_libro, name='nuevo_libro'),

    # Formularios para registrar, editar y dar de baja autores (CU-19)
    path('gestion/autores/nuevo/', views.nuevo_autor, name='nuevo_autor'),
    path('gestion/autores/<int:autor_id>/editar/', views_catalogos.editar_autor, name='editar_autor'),
    path('gestion/autores/<int:autor_id>/eliminar/', views_catalogos.eliminar_autor, name='eliminar_autor'),

    # Permite registrar, editar y dar de baja editoriales (CU-19)
    path('gestion/editoriales/nueva/', views.nueva_editorial, name='nueva_editorial'),
    path('gestion/editoriales/<int:editorial_id>/editar/', views_catalogos.editar_editorial, name='editar_editorial'),
    path('gestion/editoriales/<int:editorial_id>/eliminar/', views_catalogos.eliminar_editorial, name='eliminar_editorial'),

    # Permite registrar, editar y dar de baja categorías (CU-19)
    path('gestion/categorias/nueva/', views.nueva_categoria, name='nueva_categoria'),
    path('gestion/categorias/<int:categoria_id>/editar/', views_catalogos.editar_categoria, name='editar_categoria'),
    path('gestion/categorias/<int:categoria_id>/eliminar/', views_catalogos.eliminar_categoria, name='eliminar_categoria'),

    # Permite editar un libro registrado
    path('gestion/libros/<int:libro_id>/editar/', views.editar_libro, name='editar_libro'),

    # Permite dar de baja o reactivar libros
    path(
        'gestion/libros/<int:libro_id>/estado/',
        views.cambiar_estado_libro,
        name='cambiar_estado_libro'
    ),
]
