from django.db import models
from django.utils import timezone


class Multa(models.Model):
    MOTIVOS = [('RETRASO', 'Retraso'), ('DANIO', 'Daño'), ('PERDIDA', 'Pérdida')]
    ESTADOS = [('PENDIENTE', 'Pendiente'), ('PAGADA', 'Pagada'), ('CONDONADA', 'Condonada')]

    id = models.BigAutoField(primary_key=True)
    prestamo = models.ForeignKey('prestamos.Prestamo', models.PROTECT)
    usuario = models.ForeignKey('cuentas.Usuario', models.PROTECT)
    motivo = models.CharField(max_length=10, choices=MOTIVOS)
    dias_retraso = models.PositiveSmallIntegerField(default=0)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='PENDIENTE', db_index=True)
    fecha_generacion = models.DateTimeField(default=timezone.now)
    justificacion_condonacion = models.CharField(max_length=255, blank=True, null=True)
    condonada_por = models.ForeignKey('cuentas.Usuario', models.SET_NULL, related_name='multa_condonada_por_set', blank=True, null=True)

    class Meta:
        db_table = 'multa'
        db_table_comment = 'Multa por retraso, daño o pérdida de un ejemplar'


class Pago(models.Model):
    METODOS = [('EFECTIVO', 'Efectivo'), ('TARJETA', 'Tarjeta'), ('TRANSFERENCIA', 'Transferencia')]

    id = models.BigAutoField(primary_key=True)
    multa = models.ForeignKey(Multa, models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=15, choices=METODOS)
    folio_recibo = models.CharField(unique=True, max_length=30)
    fecha_pago = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey('cuentas.Usuario', models.PROTECT)

    class Meta:
        db_table = 'pago'
        db_table_comment = 'Pago (total o parcial) de una multa'