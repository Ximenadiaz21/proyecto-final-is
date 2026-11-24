from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.mail import send_mail
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


# Modelo principal para las cuentas de todos los usuarios de la biblioteca
class Usuario(AbstractUser):
    TIPO_CHOICES = [
        ('ESTUDIANTE', 'Estudiante'),
        ('PROFESOR', 'Profesor'),
        ('BIBLIOTECARIO', 'Bibliotecario'),
    ]

    email = models.EmailField(unique=True, max_length=254)
    tipo_usuario = models.CharField(max_length=15, choices=TIPO_CHOICES, default='ESTUDIANTE', db_index=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'usuario'
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_usuario__in=['ESTUDIANTE', 'PROFESOR', 'BIBLIOTECARIO']),
                name='chk_usuario_tipo',
            ),
        ]

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
    TIPOS = [
        ('VENCE_PRONTO', 'Vence pronto'),
        ('VENCIDO', 'Vencido'),
        ('RESERVA_DISPONIBLE', 'Reserva disponible'),
        ('MULTA', 'Multa'),
        ('GENERAL', 'General'),
    ]

    # Asuntos de correo según el tipo de notificación (RF-15)
    ASUNTOS_CORREO = {
        'VENCE_PRONTO': 'Recordatorio de vencimiento próximo - Biblioteca Escolar',
        'VENCIDO': 'Aviso de préstamo vencido - Biblioteca Escolar',
        'RESERVA_DISPONIBLE': 'Tu libro reservado ya está disponible - Biblioteca Escolar',
        'MULTA': 'Aviso de multa registrada - Biblioteca Escolar',
        'GENERAL': 'Notificación - Biblioteca Escolar',
    }

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('Usuario', models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPOS)
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
                condition=Q(tipo__in=['VENCE_PRONTO', 'VENCIDO', 'RESERVA_DISPONIBLE', 'MULTA', 'GENERAL']),
                name='chk_notificacion_tipo',
            ),
        ]

    # Envía la notificación también por correo electrónico al usuario (RF-15, CU-36)
    def enviar_correo(self):
        # Si el usuario no tiene correo registrado, no intenta enviarlo
        if not self.usuario_id or not self.usuario.email:
            return

        asunto = self.ASUNTOS_CORREO.get(self.tipo, 'Notificación - Biblioteca Escolar')
        nombre = self.usuario.get_full_name() or self.usuario.username
        cuerpo = (
            f"Hola {nombre},\n\n"
            f"{self.mensaje}\n\n"
            f"Puedes consultar tus préstamos, reservas y notificaciones iniciando sesión "
            f"en el Sistema de Gestión de Biblioteca Escolar.\n\n"
            f"Atentamente,\n"
            f"Biblioteca Escolar"
        )

        # Usa fail_silently=True para que una falla de red nunca interrumpa una transacción
        send_mail(
            subject=asunto,
            message=cuerpo,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@biblioteca.escolar.mx'),
            recipient_list=[self.usuario.email],
            fail_silently=True,
        )

    # Al crear una nueva notificación, programa el envío de correo tras confirmar la transacción (RF-15, RNF-03)
    def save(self, *args, **kwargs):
        es_nueva = self._state.adding
        super().save(*args, **kwargs)
        if es_nueva:
            transaction.on_commit(self.enviar_correo)


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
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__in=['PENDIENTE', 'APROBADA', 'RECHAZADA']),
                name='chk_sugerencia_estado',
            ),
        ]