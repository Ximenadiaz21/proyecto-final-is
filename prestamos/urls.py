from django.urls import path
from . import views
from . import views_cancelacion

urlpatterns = [
    # Solicita el préstamo de un libro
    path('solicitar/<int:libro_id>/', views.solicitar_prestamo, name='solicitar_prestamo'),

    # Muestra los préstamos del usuario
    path('mis-prestamos/', views.mis_prestamos, name='mis_prestamos'),

    # Cancela una solicitud que no se ha recogido
    path('cancelar/<int:prestamo_id>/', views_cancelacion.cancelar_solicitud, name='cancelar_solicitud'),

    # Panel del bibliotecario para entregar y recibir libros
    path('gestion/', views.gestion_prestamos, name='gestion_prestamos'),
    path('entregar/<int:prestamo_id>/', views.entregar_prestamo, name='entregar_prestamo'),
    path('devolver/<int:prestamo_id>/', views.recibir_devolucion, name='recibir_devolucion'),
]
