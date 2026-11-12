from django.urls import path
from . import views
from . import views_cancelacion
from . import views_politicas
from . import views_renovacion
from . import views_reservas

urlpatterns = [
    # Configuración de políticas de préstamo por tipo de usuario (CU-31, RF-13)
    path('politicas/', views_politicas.configurar_politicas, name='configurar_politicas'),

    # Solicita el préstamo de un libro (CU-06)
    path('solicitar/<int:libro_id>/', views.solicitar_prestamo, name='solicitar_prestamo'),

    # Muestra los préstamos y reservas del usuario (CU-09, CU-13)
    path('mis-prestamos/', views.mis_prestamos, name='mis_prestamos'),

    # Renueva un préstamo activo (CU-10)
    path('renovar/<int:prestamo_id>/', views_renovacion.renovar_prestamo, name='renovar_prestamo'),

    # Cancela una solicitud que no se ha recogido (CU-08)
    path('cancelar/<int:prestamo_id>/', views_cancelacion.cancelar_solicitud, name='cancelar_solicitud'),

    # Reserva un libro sin ejemplares disponibles y cancela reservas del lector (CU-11, CU-12)
    path('reservar/<int:libro_id>/', views_reservas.reservar_libro, name='reservar_libro'),
    path('reservas/<int:reserva_id>/cancelar/', views_reservas.cancelar_reserva, name='cancelar_reserva'),

    # Panel del bibliotecario para gestionar reservas (CU-30)
    path('reservas/gestion/', views_reservas.gestion_reservas, name='gestion_reservas'),
    path('reservas/<int:reserva_id>/atender/', views_reservas.atender_reserva, name='atender_reserva'),
    path('reservas/<int:reserva_id>/cancelar-admin/', views_reservas.cancelar_reserva_bibliotecario, name='cancelar_reserva_bibliotecario'),

    # Panel del bibliotecario para entregar, prestar en mostrador y recibir libros (CU-23, CU-24, CU-25, CU-27)
    path('gestion/', views.gestion_prestamos, name='gestion_prestamos'),
    path('mostrador/', views.registrar_prestamo_mostrador, name='registrar_prestamo_mostrador'),
    path('entregar/<int:prestamo_id>/', views.entregar_prestamo, name='entregar_prestamo'),
    path('devolver/<int:prestamo_id>/', views.recibir_devolucion, name='recibir_devolucion'),
    path('incidente/<int:prestamo_id>/', views.registrar_incidente_ejemplar, name='registrar_incidente_ejemplar'),
]
