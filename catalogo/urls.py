
from django.urls import path
from . import views

urlpatterns = [
    # Muestra los libros disponibles en la biblioteca
    path('', views.lista_libros, name='lista_libros'),

    # Abre la información completa de un libro
    path('<int:libro_id>/', views.detalle_libro, name='detalle_libro'),

    # Muestra la administración de libros para el bibliotecario
    path('gestion/', views.gestionar_libros, name='gestionar_libros'),
]
