from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Estudiante, Profesor, Carrera, Departamento

class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Información Adicional', {
            'fields': ('tipo_usuario', 'telefono', 'bloqueado', 'motivo_bloqueo'),
        }),
    )

admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Estudiante)
admin.site.register(Profesor)
admin.site.register(Carrera)
admin.site.register(Departamento)