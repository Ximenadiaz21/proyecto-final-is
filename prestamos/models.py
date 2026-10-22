from django.db import models

class PoliticaPrestamo(models.Model):
    id = models.BigAutoField(primary_key=True)
    tipo_usuario = models.CharField(unique=True, max_length=15)
    dias_prestamo = models.PositiveSmallIntegerField()
    max_libros = models.PositiveSmallIntegerField()
    max_renovaciones = models.PositiveSmallIntegerField()
    multa_por_dia = models.DecimalField(max_digits=8, decimal_places=2)
    multa_maxima = models.DecimalField(max_digits=8, decimal_places=2)
    horas_para_recoger = models.PositiveSmallIntegerField()
    actualizado_en = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'politica_prestamo'
        db_table_comment = 'Parámetros de préstamo por tipo de usuario'

class Prestamo(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('cuentas.Usuario', models.DO_NOTHING)
    ejemplar = models.ForeignKey('catalogo.Ejemplar', models.DO_NOTHING)
    estado = models.CharField(max_length=12)
    fecha_solicitud = models.DateTimeField()
    fecha_limite_recoger = models.DateTimeField(blank=True, null=True)
    fecha_prestamo = models.DateTimeField(blank=True, null=True)
    fecha_vencimiento = models.DateField(blank=True, null=True)
    fecha_devolucion = models.DateTimeField(blank=True, null=True)
    num_renovaciones = models.PositiveSmallIntegerField()
    entregado_por = models.ForeignKey('cuentas.Usuario', models.DO_NOTHING, related_name='prestamo_entregado_por_set', blank=True, null=True)
    recibido_por = models.ForeignKey('cuentas.Usuario', models.DO_NOTHING, related_name='prestamo_recibido_por_set', blank=True, null=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'prestamo'
        db_table_comment = 'Préstamo de un ejemplar a un usuario lector'

class Reserva(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('cuentas.Usuario', models.DO_NOTHING)
    libro = models.ForeignKey('catalogo.Libro', models.DO_NOTHING)
    ejemplar_asignado = models.ForeignKey('catalogo.Ejemplar', models.DO_NOTHING, blank=True, null=True)
    estado = models.CharField(max_length=12)
    fecha_reserva = models.DateTimeField()
    fecha_expiracion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'reserva'
        db_table_comment = 'Reserva de un título sin ejemplares disponibles (cola FIFO)'