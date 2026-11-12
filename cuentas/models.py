from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


# Modelo principal para las cuentas de todos los usuarios de la biblioteca
class Usuario(AbstractUser):
    TIPO_CHOICES = [
        ('ESTUDIANTE', 'Estudiante'),
        ('PROFESOR', 'Profesor'),
        ('BIBLIOTECARIO', 'Bibliotecario'),
    ]

    tipo_usuario = models.CharField(max_length=15, choices=TIPO_CHOICES, default='BIBLIOTECARIO')
    telefono = models.CharField(max_length=20, null=True, blank=True)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'usuario'

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
    semestre = models.PositiveIntegerField()

    class Meta:
        db_table = 'estudiante'
        db_table_comment = 'Perfil de estudiante (1 a 1 con usuario)'


class Profesor(models.Model):
    usuario = models.OneToOneField('Usuario', models.CASCADE, primary_key=True)
    num_empleado = models.CharField(unique=True, max_length=20)
    departamento = models.ForeignKey(Departamento, models.PROTECT)

    class Meta:
        db_table = 'profesor'
        db_table_comment = 'Perfil de profesor (1 a 1 con usuario)'


class Notificacion(models.Model):
    TIPOS = [
        ('VENCE_PRONTO', 'Vence pronto'),
        ('VENCIDO', 'Vencido'),
        ('RESERVA_DISPONIBLE', 'Reserva disponible'),
        ('MULTA', 'Multa'),
        ('GENERAL', 'General'),
    ]

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('Usuario', models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    mensaje = models.CharField(max_length=500)
    leida = models.BooleanField(default=False)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'notificacion'
        ordering = ['-fecha']


class SugerenciaAdquisicion(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADA', 'Aprobada'),
        ('RECHAZADA', 'Rechazada'),
    ]

    id = models.BigAutoField(primary_key=True)
    profesor = models.ForeignKey('Profesor', models.PROTECT)
    titulo = models.CharField(max_length=255)
    autores = models.CharField(max_length=255)
    isbn = models.CharField(max_length=13, blank=True, null=True)
    justificacion = models.TextField()
    estado = models.CharField(max_length=10, choices=ESTADOS, default='PENDIENTE')
    respuesta = models.CharField(max_length=255, blank=True, null=True)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sugerencia_adquisicion'
        db_table_comment = 'Sugerencias de compra enviadas por profesores'