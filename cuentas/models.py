from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.db.models import Q
from django.utils import timezone

GRUPO_BIBLIOTECARIOS = 'Bibliotecarios'


# Modelo principal para las cuentas de todos los usuarios de la biblioteca
class Usuario(AbstractUser):
    class Tipo(models.TextChoices):
        ESTUDIANTE = 'ESTUDIANTE', 'Estudiante'
        PROFESOR = 'PROFESOR', 'Profesor'
        BIBLIOTECARIO = 'BIBLIOTECARIO', 'Bibliotecario'

    TIPO_CHOICES = Tipo.choices

    email = models.EmailField(unique=True, max_length=254)
    tipo_usuario = models.CharField(
        max_length=15,
        choices=Tipo.choices,
        default=Tipo.ESTUDIANTE,
        db_index=True,
    )
    telefono = models.CharField(max_length=20, null=True, blank=True)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=255, null=True, blank=True)

    # createsuperuser solicita correo y rol para evitar superusuarios con tipo incorrecto
    REQUIRED_FIELDS = ['email', 'tipo_usuario']

    class Meta:
        db_table = 'usuario'
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_usuario__in=['ESTUDIANTE', 'PROFESOR', 'BIBLIOTECARIO']),
                name='chk_usuario_tipo',
            ),
        ]

    @property
    def es_bibliotecario(self):
        return (self.tipo_usuario == self.Tipo.BIBLIOTECARIO or self.is_superuser) and not self.bloqueado

    @property
    def es_lector(self):
        return self.tipo_usuario in (self.Tipo.ESTUDIANTE, self.Tipo.PROFESOR)

    @property
    def es_profesor(self):
        return self.tipo_usuario == self.Tipo.PROFESOR

    # Mantiene sincronizados is_staff y el grupo «Bibliotecarios» con el rol del usuario
    def save(self, *args, **kwargs):
        campos = kwargs.get('update_fields')
        actualizar_rol = campos is None or 'tipo_usuario' in campos or 'is_superuser' in campos
        es_biblio = self.tipo_usuario == self.Tipo.BIBLIOTECARIO

        if actualizar_rol:
            self.is_staff = es_biblio or self.is_superuser
            if campos is not None and 'is_staff' not in campos:
                kwargs['update_fields'] = list(campos) + ['is_staff']

        super().save(*args, **kwargs)

        if actualizar_rol:
            grupo = Group.objects.filter(name=GRUPO_BIBLIOTECARIOS).first()
            if grupo:
                if es_biblio:
                    self.groups.add(grupo)
                else:
                    self.groups.remove(grupo)

    def __str__(self):
        return f"{self.username} - {self.get_tipo_usuario_display()}"


class Carrera(models.Model):
    id = models.BigAutoField(primary_key=True)
    clave = models.CharField(unique=True, max_length=10)
    nombre = models.CharField(max_length=120)

    class Meta:
        db_table = 'carrera'
        db_table_comment = 'Carreras de la escuela'

    def __str__(self):
        return self.nombre


class Departamento(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=120)

    class Meta:
        db_table = 'departamento'
        db_table_comment = 'Departamentos académicos'

    def __str__(self):
        return self.nombre


class Estudiante(models.Model):
    usuario = models.OneToOneField('Usuario', models.CASCADE, primary_key=True)
    matricula = models.CharField(unique=True, max_length=20)
    carrera = models.ForeignKey(Carrera, models.PROTECT)
    semestre = models.PositiveSmallIntegerField()

    class Meta:
        db_table = 'estudiante'
        db_table_comment = 'Perfil de estudiante (1 a 1 con usuario)'
        constraints = [
            models.CheckConstraint(
                condition=Q(semestre__gte=1, semestre__lte=12),
                name='chk_estudiante_semestre',
            ),
        ]


class Profesor(models.Model):
    usuario = models.OneToOneField('Usuario', models.CASCADE, primary_key=True)
    num_empleado = models.CharField(unique=True, max_length=20)
    departamento = models.ForeignKey(Departamento, models.PROTECT)

    class Meta:
        db_table = 'profesor'
        db_table_comment = 'Perfil de profesor (1 a 1 con usuario)'


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        VENCE_PRONTO = 'VENCE_PRONTO', 'Vence pronto'
        VENCIDO = 'VENCIDO', 'Vencido'
        RESERVA_DISPONIBLE = 'RESERVA_DISPONIBLE', 'Reserva disponible'
        MULTA = 'MULTA', 'Multa'
        GENERAL = 'GENERAL', 'General'

    TIPOS = Tipo.choices

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('Usuario', models.CASCADE)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.GENERAL)
    mensaje = models.CharField(max_length=500)
    leida = models.BooleanField(default=False)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'notificacion'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['usuario', 'leida'], name='idx_notificacion_usuario_leida'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    tipo__in=['VENCE_PRONTO', 'VENCIDO', 'RESERVA_DISPONIBLE', 'MULTA', 'GENERAL']
                ),
                name='chk_notificacion_tipo',
            ),
        ]


class SugerenciaAdquisicion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        APROBADA = 'APROBADA', 'Aprobada'
        RECHAZADA = 'RECHAZADA', 'Rechazada'

    ESTADOS = Estado.choices

    id = models.BigAutoField(primary_key=True)
    profesor = models.ForeignKey('Profesor', models.CASCADE)
    titulo = models.CharField(max_length=255)
    autores = models.CharField(max_length=255)
    isbn = models.CharField(max_length=13, blank=True, null=True)
    justificacion = models.TextField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    respuesta = models.CharField(max_length=255, blank=True, null=True)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sugerencia_adquisicion'
        db_table_comment = 'Sugerencias de compra enviadas por profesores'
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__in=['PENDIENTE', 'APROBADA', 'RECHAZADA']),
                name='chk_sugerencia_estado',
            ),
        ]