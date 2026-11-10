from django.urls import path
from . import views

urlpatterns = [
    # Abre el catálogo de libros
    path('', views.lista_libros, name='lista_libros'),
]