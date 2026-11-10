from django.contrib import admin
from .models import PoliticaPrestamo, Prestamo, Reserva


@admin.register(PoliticaPrestamo)
class PoliticaPrestamoAdmin(admin.ModelAdmin):
    list_display = (
        'tipo_usuario', 'dias_prestamo', 'max_libros', 'max_renovaciones',
        'multa_por_dia', 'multa_maxima', 'horas_para_recoger',
    )


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    # Columnas que se ven en la lista de préstamos
    list_display = (
        'id', 'libro', 'usuario', 'codigo_ejemplar', 'estado',
        'fecha_prestamo', 'fecha_vencimiento', 'fecha_devolucion',
    )
    list_display_links = ('id', 'libro')

    # Permite cambiar la fecha de vencimiento directo desde la lista
    list_editable = ('fecha_vencimiento',)

    list_filter = ('estado',)
    search_fields = (
        'usuario__username', 'usuario__first_name', 'usuario__last_name',
        'ejemplar__codigo_inventario', 'ejemplar__libro__titulo',
    )
    ordering = ('-id',)
    list_select_related = ('usuario', 'ejemplar', 'ejemplar__libro')

    @admin.display(description='Libro', ordering='ejemplar__libro__titulo')
    def libro(self, obj):
        return obj.ejemplar.libro.titulo

    @admin.display(description='Ejemplar', ordering='ejemplar__codigo_inventario')
    def codigo_ejemplar(self, obj):
        return obj.ejemplar.codigo_inventario


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('id', 'libro', 'usuario', 'estado', 'fecha_reserva', 'fecha_expiracion')
    list_filter = ('estado',)
    search_fields = ('usuario__username', 'libro__titulo')
    ordering = ('-id',)
    list_select_related = ('usuario', 'libro')