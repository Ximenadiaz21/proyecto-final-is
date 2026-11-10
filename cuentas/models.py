
from django.db import models
from django.contrib.auth.models import AbstractUser


# Modelo principal para las cuentas de todos los usuarios de la biblioteca
class Usuario(AbstractUser):

    # Define los tres tipos de usuarios que pueden acceder al sistema
    TIPO_CHOICES = [
        ('ESTUDIANTE', 'Estudiante'),
        ('PROFESOR', 'Profesor'),
        ('BIBLIOTECARIO', 'Bibliotecario'),
    ]

    # Guarda el rol del usuario para determinar sus permisos
    tipo_usuario = models.CharField(max_length=15, choices=TIPO_CHOICES, default='BIBLIOTECARIO')

    # Información de contacto y estado administrativo de la cuenta
    telefono = models.CharField(max_length=20, null=True, blank=True)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        # Utiliza la tabla usuario que ya existe en MySQL
        db_table = 'usuario'
        managed = False

    def __str__(self):
        # Muestra el nombre de usuario y su rol
        return f"{self.username} - {self.get_tipo_usuario_display()}"


# Guarda las carreras a las que pueden pertenecer los estudiantes
class Carrera(models.Model):
    id = models.BigAutoField(primary_key=True)
    clave = models.CharField(unique=True, max_length=10)
    nombre = models.CharField(max_length=120)

    class Meta:
        managed = False
        db_table = 'carrera'
        db_table_comment = 'Carreras de la escuela'


# Guarda los departamentos a los que pertenecen los profesores
class Departamento(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=120)

    class Meta:
        managed = False
        db_table = 'departamento'
        db_table_comment = 'Departamentos académicos'


# Guarda la información escolar de los usuarios con rol de estudiante
class Estudiante(models.Model):

    # Cada estudiante está relacionado con una sola cuenta de usuario
    usuario = models.OneToOneField('Usuario', models.DO_NOTHING, primary_key=True)

    # La matrícula identifica al estudiante y la carrera indica qué estudia
    matricula = models.CharField(unique=True, max_length=20)
    carrera = models.ForeignKey(Carrera, models.DO_NOTHING)
    semestre = models.PositiveIntegerField()

    class Meta:
        managed = False
        db_table = 'estudiante'
        db_table_comment = 'Perfil de estudiante (1 a 1 con usuario)'


# Guarda la información laboral de los usuarios con rol de profesor
class Profesor(models.Model):

    # Cada profesor está relacionado con una sola cuenta de usuario
    usuario = models.OneToOneField('Usuario', models.DO_NOTHING, primary_key=True)

    # Identifica al profesor y el departamento académico al que pertenece
    num_empleado = models.CharField(unique=True, max_length=20)
    departamento = models.ForeignKey(Departamento, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'profesor'
        db_table_comment = 'Perfil de profesor (1 a 1 con usuario)'


# Almacena los avisos que recibe cada usuario dentro del sistema
class Notificacion(models.Model):
    id = models.BigAutoField(primary_key=True)

    # Relaciona cada notificación con el usuario que debe recibirla
    usuario = models.ForeignKey('Usuario', models.DO_NOTHING)

    # Guarda el tipo de aviso, su contenido y si ya fue leído
    tipo = models.CharField(max_length=20)
    mensaje = models.CharField(max_length=500)
    leida = models.IntegerField()
    fecha = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'notificacion'
        