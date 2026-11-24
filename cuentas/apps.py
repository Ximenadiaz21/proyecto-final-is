from django.apps import AppConfig
from django.db.models.signals import post_migrate

APPS_BIBLIOTECA = ('cuentas', 'catalogo', 'prestamos', 'multas')
# RN-16: los registros históricos de préstamos, multas y pagos no se eliminan
PERMISOS_PROTEGIDOS = ('delete_prestamo', 'delete_multa', 'delete_pago')


# Crea o actualiza el grupo «Bibliotecarios» con permisos de administración tras cada migrate
def crear_grupo_bibliotecarios(sender, **kwargs):
    from django.contrib.auth.models import Group, Permission
    from .models import GRUPO_BIBLIOTECARIOS

    grupo, _ = Group.objects.get_or_create(name=GRUPO_BIBLIOTECARIOS)
    permisos = Permission.objects.filter(
        content_type__app_label__in=APPS_BIBLIOTECA,
    ).exclude(codename__in=PERMISOS_PROTEGIDOS)
    grupo.permissions.set(permisos)


class CuentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cuentas'

    def ready(self):
        post_migrate.connect(crear_grupo_bibliotecarios, sender=self)
