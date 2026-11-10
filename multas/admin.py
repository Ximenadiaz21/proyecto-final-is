from django.contrib import admin
from .models import Multa, Pago


@admin.register(Multa)
class MultaAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'libro', 'usuario', 'motivo', 'dias_retraso',
        'monto', 'estado', 'fecha_generacion',
    )
    list_display_links = ('id', 'libro')
    list_filter = ('estado', 'motivo')
    search_fields = (
        'usuario__username', 'usuario__first_name', 'usuario__last_name',
        'prestamo__ejemplar__libro__titulo',
    )
    ordering = ('-id',)
    list_select_related = ('usuario', 'prestamo__ejemplar__libro')

    @admin.display(description='Libro')
    def libro(self, obj):
        return obj.prestamo.ejemplar.libro.titulo


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'folio_recibo', 'multa', 'monto', 'metodo', 'fecha_pago', 'registrado_por')
    list_filter = ('metodo',)
    search_fields = ('folio_recibo', 'multa__usuario__username')
    ordering = ('-id',)