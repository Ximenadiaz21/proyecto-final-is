from django.urls import path

from . import views

urlpatterns = [
    # Panel principal con los 4 reportes operativos de la biblioteca (CU-32, RF-14)
    path('', views.reportes, name='reportes'),

    # Descarga en formato CSV de cualquiera de los 4 reportes (prestamos, libros, vencidos, multas)
    path('exportar/<str:tipo>/', views.exportar_reporte_csv, name='exportar_reporte_csv'),
]
