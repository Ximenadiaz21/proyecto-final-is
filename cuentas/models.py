from django.db import models
from django.contrib.auth.models import AbstractUser

class Usuario(AbstractUser):
    TIPO_CHOICES = [
        ('ESTUDIANTE', 'Estudiante'),
        ('PROFESOR', 'Profesor'),
        ('BIBLIOTECARIO', 'Bibliotecario'),
    ]
    
    tipo_usuario = models.CharField(max_length=15, choices=TIPO_CHOICES)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'usuario'
        managed = False

    def __str__(self):
        return f"{self.username} - {self.get_tipo_usuario_display()}"

class Carrera(models.Model):
    id = models.BigAutoField(primary_key=True)
    clave = models.CharField(unique=True, max_length=10)
    nombre = models.CharField(max_length=120)

    class Meta:
        managed = False
        db_table = 'carrera'
        db_table_comment = 'Carreras de la escuela'

class Departamento(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=120)

    class Meta:
        managed = False
        db_table = 'departamento'
        db_table_comment = 'Departamentos acadÚmicos'

class Estudiante(models.Model):
    usuario = models.OneToOneField('Usuario', models.DO_NOTHING, primary_key=True)
    matricula = models.CharField(unique=True, max_length=20)
    carrera = models.ForeignKey(Carrera, models.DO_NOTHING)
    semestre = models.PositiveIntegerField()

    class Meta:
        managed = False
        db_table = 'estudiante'
        db_table_comment = 'Perfil de estudiante (1 a 1 con usuario)'

class Profesor(models.Model):
    usuario = models.OneToOneField('Usuario', models.DO_NOTHING, primary_key=True)
    num_empleado = models.CharField(unique=True, max_length=20)
    departamento = models.ForeignKey(Departamento, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'profesor'
        db_table_comment = 'Perfil de profesor (1 a 1 con usuario)'

class Notificacion(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('Usuario', models.DO_NOTHING)
    tipo = models.CharField(max_length=20)
    mensaje = models.CharField(max_length=500)
    leida = models.IntegerField()
    fecha = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'notificacion'