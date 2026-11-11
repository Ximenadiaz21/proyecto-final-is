from django.urls import path
from . import views_usuarios as vistas

urlpatterns = [
    # Lista de usuarios
    path('', vistas.gestion_usuarios, name='gestion_usuarios'),

    # Alta y edición
    path('nuevo/', vistas.nuevo_usuario, name='nuevo_usuario'),
    path('<int:usuario_id>/editar/', vistas.editar_usuario, name='editar_usuario'),

    # Bloquear o desbloquear
    path('<int:usuario_id>/bloqueo/', vistas.cambiar_bloqueo, name='cambiar_bloqueo'),

    # Carga masiva desde CSV
    path('importar/', vistas.importar_usuarios, name='importar_usuarios'),
    path('importar/plantilla/', vistas.plantilla_csv, name='plantilla_csv'),
]
