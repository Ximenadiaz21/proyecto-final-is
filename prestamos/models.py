from django.db import models
from django.utils import timezone


class PoliticaPrestamo(models.Model):
    TIPOS = [('ESTUDIANTE', 'Estudiante'), ('PROFESOR', 'Profesor')]

    id = models.BigAutoField(primary_key=True)
    tipo_usuario = models.CharField(unique=True, max_length=15, choices=TIPOS)
    dias_prestamo = models.PositiveSmallIntegerField()
    max_libros = models.PositiveSmallIntegerField()
    max_renovaciones = models.PositiveSmallIntegerField()
    multa_por_dia = models.DecimalField(max_digits=8, decimal_places=2)
    multa_maxima = models.DecimalField(max_digits=8, decimal_places=2)
    horas_para_recoger = models.PositiveSmallIntegerField()
    actualizado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'politica_prestamo'
        db_table_comment = 'Parámetros de préstamo por tipo de usuario'


class Prestamo(models.Model):
    ESTADOS = [
        ('SOLICITADO', 'Solicitado'),
        ('ACTIVO', 'Activo'),
        ('VENCIDO', 'Vencido'),
        ('DEVUELTO', 'Devuelto'),
        ('CANCELADO', 'Cancelado'),
        ('EXPIRADO', 'Expirado'),
        ('PERDIDO', 'Perdido'),
    ]

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('cuentas.Usuario', models.PROTECT)
    ejemplar = models.ForeignKey('catalogo.Ejemplar', models.PROTECT)
    estado = models.CharField(max_length=12, choices=ESTADOS, db_index=True)
    fecha_solicitud = models.DateTimeField(default=timezone.now)
    fecha_limite_recoger = models.DateTimeField(blank=True, null=True)
    fecha_prestamo = models.DateTimeField(blank=True, null=True)
    fecha_vencimiento = models.DateField(blank=True, null=True, db_index=True)
    fecha_devolucion = models.DateTimeField(blank=True, null=True)
    num_renovaciones = models.PositiveSmallIntegerField(default=0)
    entregado_por = models.ForeignKey('cuentas.Usuario', models.SET_NULL, related_name='prestamo_entregado_por_set', blank=True, null=True)
    recibido_por = models.ForeignKey('cuentas.Usuario', models.SET_NULL, related_name='prestamo_recibido_por_set', blank=True, null=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'prestamo'
        db_table_comment = 'Préstamo de un ejemplar a un usuario lector'


class Reserva(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('DISPONIBLE', 'Disponible'),
        ('ATENDIDA', 'Atendida'),
        ('CANCELADA', 'Cancelada'),
        ('EXPIRADA', 'Expirada'),
    ]

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('cuentas.Usuario', models.PROTECT)
    libro = models.ForeignKey('catalogo.Libro', models.PROTECT)
    ejemplar_asignado = models.ForeignKey('catalogo.Ejemplar', models.SET_NULL, blank=True, null=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='PENDIENTE', db_index=True)
    fecha_reserva = models.DateTimeField(default=timezone.now)
    fecha_expiracion = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'reserva'
        db_table_comment = 'Reserva de un título sin ejemplares disponibles (cola FIFO)'