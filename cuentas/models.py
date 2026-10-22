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