from django.urls import path
from . import views

urlpatterns = [
    path('solicitar/<int:libro_id>/', views.solicitar_prestamo, name='solicitar_prestamo'),
]