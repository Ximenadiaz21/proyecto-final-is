from django.contrib import admin
from .models import PoliticaPrestamo, Prestamo, Reserva

admin.site.register(PoliticaPrestamo)
admin.site.register(Prestamo)
admin.site.register(Reserva)