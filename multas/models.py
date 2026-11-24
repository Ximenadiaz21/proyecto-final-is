from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class Multa(models.Model):
    class Motivo(models.TextChoices):
        RETRASO = 'RETRASO', 'Retraso'
        DANIO = 'DANIO', 'Daño'
        PERDIDA = 'PERDIDA', 'Pérdida'

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PAGADA = 'PAGADA', 'Pagada'
        CONDONADA = 'CONDONADA', 'Condonada'

    MOTIVOS = Motivo.choices
    ESTADOS = Estado.choices

    id = models.BigAutoField(primary_key=True)
    prestamo = models.ForeignKey('prestamos.Prestamo', models.PROTECT)
    usuario = models.ForeignKey('cuentas.Usuario', models.PROTECT)
    motivo = models.CharField(max_length=10, choices=Motivo.choices)
    dias_retraso = models.PositiveSmallIntegerField(default=0)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        db_index=True,
    )
    fecha_generacion = models.DateTimeField(default=timezone.now)
    justificacion_condonacion = models.CharField(max_length=255, blank=True, null=True)
    condonada_por = models.ForeignKey(
        'cuentas.Usuario',
        models.SET_NULL,
        related_name='multa_condonada_por_set',
        blank=True,
        null=True,
    )

    class Meta:
        db_table = 'multa'
        db_table_comment = 'Multa por retraso, daño o pérdida de un ejemplar'
        indexes = [
            models.Index(fields=['usuario', 'estado'], name='idx_multa_usuario_estado'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(motivo__in=['RETRASO', 'DANIO', 'PERDIDA']),
                name='chk_multa_motivo',
            ),
            models.CheckConstraint(
                condition=Q(estado__in=['PENDIENTE', 'PAGADA', 'CONDONADA']),
                name='chk_multa_estado',
            ),
            models.CheckConstraint(
                condition=Q(monto__gt=0),
                name='chk_multa_monto_positivo',
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(estado='CONDONADA')
                    | (
                        Q(justificacion_condonacion__isnull=False)
                        & ~Q(justificacion_condonacion='')
                    )
                ),
                name='chk_multa_condonacion_justificada',
            ),
        ]

    # Valida RN-14 incluso desde Django Admin antes de guardar
    def clean(self):
        super().clean()
        if self.estado == 'CONDONADA' and not (self.justificacion_condonacion or '').strip():
            raise ValidationError({
                'justificacion_condonacion': (
                    'La justificación es obligatoria para condonar una multa (RN-14).'
                )
            })

    # Suma los pagos registrados para esta multa
    def total_pagado(self):
        return self.pago_set.aggregate(t=Sum('monto'))['t'] or Decimal('0.00')

    # Calcula el saldo pendiente de cobro de esta multa
    def saldo(self):
        if self.estado == self.Estado.CONDONADA:
            return Decimal('0.00')
        return max(self.monto - self.total_pagado(), Decimal('0.00'))


class Pago(models.Model):
    class Metodo(models.TextChoices):
        EFECTIVO = 'EFECTIVO', 'Efectivo'
        TARJETA = 'TARJETA', 'Tarjeta'
        TRANSFERENCIA = 'TRANSFERENCIA', 'Transferencia'

    METODOS = Metodo.choices

    id = models.BigAutoField(primary_key=True)
    multa = models.ForeignKey(Multa, models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=15, choices=Metodo.choices)
    folio_recibo = models.CharField(unique=True, max_length=30)
    fecha_pago = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey('cuentas.Usuario', models.PROTECT)

    class Meta:
        db_table = 'pago'
        db_table_comment = 'Pago (total o parcial) de una multa'
        constraints = [
            models.CheckConstraint(
                condition=Q(metodo__in=['EFECTIVO', 'TARJETA', 'TRANSFERENCIA']),
                name='chk_pago_metodo',
            ),
            models.CheckConstraint(
                condition=Q(monto__gt=0),
                name='chk_pago_monto_positivo',
            ),
        ]