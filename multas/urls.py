from django.urls import path
from . import views

urlpatterns = [
    # Panel del bibliotecario para cobrar o condonar multas
    path('', views.gestion_multas, name='gestion_multas'),

    # Multas del usuario lector
    path('mis-multas/', views.mis_multas, name='mis_multas'),

    # Acciones del bibliotecario
    path('pagar/<int:multa_id>/', views.registrar_pago, name='registrar_pago'),
    path('condonar/<int:multa_id>/', views.condonar_multa, name='condonar_multa'),
]
