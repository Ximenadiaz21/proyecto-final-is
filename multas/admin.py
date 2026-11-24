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
    # El estado se gestiona con los servicios de pago/condonación (RN-14)
    readonly_fields = ('estado',)

    @admin.display(description='Libro')
    def libro(self, obj):
        return obj.prestamo.ejemplar.libro.titulo

    # RN-16: Los registros de multas no se eliminan físicamente
    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        acciones = super().get_actions(request)
        acciones.pop('delete_selected', None)
        return acciones


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'folio_recibo', 'multa', 'monto', 'metodo', 'fecha_pago', 'registrado_por')
    list_filter = ('metodo',)
    search_fields = ('folio_recibo', 'multa__usuario__username')
    ordering = ('-id',)

    # RN-16: Los pagos de multas se conservan para historial y reportes
    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        acciones = super().get_actions(request)
        acciones.pop('delete_selected', None)
        return acciones