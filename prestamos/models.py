from django.db import models
from django.db.models import Q
from django.utils import timezone


class PoliticaPrestamo(models.Model):
    class TipoUsuario(models.TextChoices):
        ESTUDIANTE = 'ESTUDIANTE', 'Estudiante'
        PROFESOR = 'PROFESOR', 'Profesor'

    TIPOS = TipoUsuario.choices

    id = models.BigAutoField(primary_key=True)
    tipo_usuario = models.CharField(unique=True, max_length=15, choices=TipoUsuario.choices)
    dias_prestamo = models.PositiveSmallIntegerField()
    max_libros = models.PositiveSmallIntegerField()
    max_renovaciones = models.PositiveSmallIntegerField()
    multa_por_dia = models.DecimalField(max_digits=8, decimal_places=2)
    multa_maxima = models.DecimalField(max_digits=8, decimal_places=2)
    horas_para_recoger = models.PositiveSmallIntegerField()
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'politica_prestamo'
        db_table_comment = 'Parámetros de préstamo por tipo de usuario'
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_usuario__in=['ESTUDIANTE', 'PROFESOR']),
                name='chk_politica_tipo_usuario',
            ),
            models.CheckConstraint(
                condition=Q(multa_por_dia__gte=0, multa_maxima__gte=0),
                name='chk_politica_multas_no_negativas',
            ),
        ]


class Prestamo(models.Model):
    class Estado(models.TextChoices):
        SOLICITADO = 'SOLICITADO', 'Solicitado'
        ACTIVO = 'ACTIVO', 'Activo'
        VENCIDO = 'VENCIDO', 'Vencido'
        DEVUELTO = 'DEVUELTO', 'Devuelto'
        CANCELADO = 'CANCELADO', 'Cancelado'
        EXPIRADO = 'EXPIRADO', 'Expirado'
        PERDIDO = 'PERDIDO', 'Perdido'

    ESTADOS = Estado.choices

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('cuentas.Usuario', models.PROTECT)
    ejemplar = models.ForeignKey('catalogo.Ejemplar', models.PROTECT)
    estado = models.CharField(max_length=12, choices=Estado.choices, db_index=True)
    fecha_solicitud = models.DateTimeField(default=timezone.now)
    fecha_limite_recoger = models.DateTimeField(blank=True, null=True)
    fecha_prestamo = models.DateTimeField(blank=True, null=True)
    fecha_vencimiento = models.DateField(blank=True, null=True, db_index=True)
    fecha_devolucion = models.DateTimeField(blank=True, null=True)
    num_renovaciones = models.PositiveSmallIntegerField(default=0)
    entregado_por = models.ForeignKey(
        'cuentas.Usuario',
        models.SET_NULL,
        related_name='prestamo_entregado_por_set',
        blank=True,
        null=True,
    )
    recibido_por = models.ForeignKey(
        'cuentas.Usuario',
        models.SET_NULL,
        related_name='prestamo_recibido_por_set',
        blank=True,
        null=True,
    )
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'prestamo'
        db_table_comment = 'Préstamo de un ejemplar a un usuario lector'
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    estado__in=[
                        'SOLICITADO', 'ACTIVO', 'VENCIDO', 'DEVUELTO',
                        'CANCELADO', 'EXPIRADO', 'PERDIDO',
                    ]
                ),
                name='chk_prestamo_estado',
            ),
        ]

    # Calcula los días naturales de retraso respecto a la fecha de vencimiento (RN-07)
    def dias_retraso(self, fecha=None):
        fecha = fecha or timezone.localdate()
        if self.fecha_vencimiento is None:
            return 0
        return max((fecha - self.fecha_vencimiento).days, 0)

    # Calcula el monto de la multa por retraso aplicando el tope máximo (RN-07)
    def calcular_multa(self, politica, fecha=None):
        if fecha is None and self.fecha_devolucion:
            fecha = timezone.localtime(self.fecha_devolucion).date()
        dias = self.dias_retraso(fecha)
        return min(dias * politica.multa_por_dia, politica.multa_maxima)


class Reserva(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        DISPONIBLE = 'DISPONIBLE', 'Disponible'
        ATENDIDA = 'ATENDIDA', 'Atendida'
        CANCELADA = 'CANCELADA', 'Cancelada'
        EXPIRADA = 'EXPIRADA', 'Expirada'

    ESTADOS = Estado.choices

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('cuentas.Usuario', models.PROTECT)
    libro = models.ForeignKey('catalogo.Libro', models.PROTECT)
    ejemplar_asignado = models.ForeignKey('catalogo.Ejemplar', models.SET_NULL, blank=True, null=True)
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        db_index=True,
    )
    fecha_reserva = models.DateTimeField(default=timezone.now)
    fecha_expiracion = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'reserva'
        db_table_comment = 'Reserva de un título sin ejemplares disponibles (cola FIFO)'
        ordering = ['fecha_reserva', 'id']
        indexes = [
            models.Index(fields=['libro', 'fecha_reserva'], name='idx_reserva_libro_fecha'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    estado__in=['PENDIENTE', 'DISPONIBLE', 'ATENDIDA', 'CANCELADA', 'EXPIRADA']
                ),
                name='chk_reserva_estado',
            ),
        ]