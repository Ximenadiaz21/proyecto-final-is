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

    # Baja lógica o reactivación (CU-20, RF-11)
    path('<int:usuario_id>/estado/', vistas.cambiar_estado_usuario, name='cambiar_estado_usuario'),

    # Carga masiva desde CSV
    path('importar/', vistas.importar_usuarios, name='importar_usuarios'),
    path('importar/plantilla/', vistas.plantilla_csv, name='plantilla_csv'),
]
