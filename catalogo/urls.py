
from django.urls import path
from . import views

urlpatterns = [
    # Muestra el catálogo de libros
    path('', views.lista_libros, name='lista_libros'),

    # Muestra la información detallada de un libro
    path('<int:libro_id>/', views.detalle_libro, name='detalle_libro'),

    # Administración del catálogo
    path('gestion/', views.gestionar_libros, name='gestionar_libros'),

    # Formulario para registrar nuevos libros
    path('gestion/nuevo/', views.nuevo_libro, name='nuevo_libro'),

    # Formulario para registrar nuevos autores
    path('gestion/autores/nuevo/', views.nuevo_autor, name='nuevo_autor'),

    # Permite registrar nuevas editoriales
    path('gestion/editoriales/nueva/', views.nueva_editorial, name='nueva_editorial'),

    # Permite registrar nuevas categorías
    path('gestion/categorias/nueva/', views.nueva_categoria, name='nueva_categoria'),

    # Permite editar un libro registrado
    path('gestion/libros/<int:libro_id>/editar/', views.editar_libro, name='editar_libro'),

    # Permite dar de baja o reactivar libros
    path(
        'gestion/libros/<int:libro_id>/estado/',
        views.cambiar_estado_libro,
        name='cambiar_estado_libro'
    ),
]
