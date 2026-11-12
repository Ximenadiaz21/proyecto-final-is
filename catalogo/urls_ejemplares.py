from django.urls import path
from . import views_ejemplares as vistas

urlpatterns = [
    # Lista de ejemplares
    path('', vistas.gestion_ejemplares, name='gestion_ejemplares'),

    # Alta y edición
    path('nuevo/', vistas.nuevo_ejemplar, name='nuevo_ejemplar'),
    path('<int:ejemplar_id>/editar/', vistas.editar_ejemplar, name='editar_ejemplar'),

    # Cambio rápido de estado
    path('<int:ejemplar_id>/estado/', vistas.cambiar_estado_ejemplar, name='cambiar_estado_ejemplar'),
]