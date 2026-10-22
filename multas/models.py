from django.db import models

# Create your models here.

class Multa(models.Model):
    id = models.BigAutoField(primary_key=True)
    prestamo = models.ForeignKey('prestamos.Prestamo', models.DO_NOTHING)
    usuario = models.ForeignKey('cuentas.Usuario', models.DO_NOTHING)
    motivo = models.CharField(max_length=10)
    dias_retraso = models.PositiveSmallIntegerField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=10)
    fecha_generacion = models.DateTimeField()
    justificacion_condonacion = models.CharField(max_length=255, blank=True, null=True)
    condonada_por = models.ForeignKey('cuentas.Usuario', models.DO_NOTHING, related_name='multa_condonada_por_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'multa'
        db_table_comment = 'Multa por retraso, da±o o pÚrdida de un ejemplar'

class Pago(models.Model):
    id = models.BigAutoField(primary_key=True)
    multa = models.ForeignKey(Multa, models.DO_NOTHING)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=15)
    folio_recibo = models.CharField(unique=True, max_length=30)
    fecha_pago = models.DateTimeField()
    registrado_por = models.ForeignKey('cuentas.Usuario', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'pago'
        db_table_comment = 'Pago (total o parcial) de una multa'