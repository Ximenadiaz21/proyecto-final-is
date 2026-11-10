from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Estudiante, Profesor, Carrera, Departamento, Notificacion


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Información Adicional', {
            'fields': ('tipo_usuario', 'telefono', 'bloqueado', 'motivo_bloqueo'),
        }),
    )

    list_display = (
        'username', 'first_name', 'last_name', 'email',
        'tipo_usuario', 'bloqueado', 'is_active',
    )
    list_filter = ('tipo_usuario', 'bloqueado', 'is_active', 'is_staff')


@admin.register(Estudiante)
class EstudianteAdmin(admin.ModelAdmin):
    list_display = ('matricula', 'nombre', 'usuario_username', 'carrera_nombre', 'semestre')
    list_filter = ('carrera', 'semestre')
    search_fields = (
        'matricula', 'usuario__username',
        'usuario__first_name', 'usuario__last_name',
    )
    list_select_related = ('usuario', 'carrera')

    @admin.display(description='Nombre')
    def nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username

    @admin.display(description='Usuario', ordering='usuario__username')
    def usuario_username(self, obj):
        return obj.usuario.username

    @admin.display(description='Carrera', ordering='carrera__nombre')
    def carrera_nombre(self, obj):
        return obj.carrera.nombre


@admin.register(Profesor)
class ProfesorAdmin(admin.ModelAdmin):
    list_display = ('num_empleado', 'nombre', 'usuario_username', 'departamento_nombre')
    list_filter = ('departamento',)
    search_fields = (
        'num_empleado', 'usuario__username',
        'usuario__first_name', 'usuario__last_name',
    )
    list_select_related = ('usuario', 'departamento')

    @admin.display(description='Nombre')
    def nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username

    @admin.display(description='Usuario', ordering='usuario__username')
    def usuario_username(self, obj):
        return obj.usuario.username

    @admin.display(description='Departamento', ordering='departamento__nombre')
    def departamento_nombre(self, obj):
        return obj.departamento.nombre


@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ('id', 'clave', 'nombre')
    search_fields = ('clave', 'nombre')


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'tipo', 'mensaje', 'leida', 'fecha')
    list_filter = ('tipo', 'leida')
    search_fields = ('usuario__username', 'mensaje')
    ordering = ('-id',)
    list_select_related = ('usuario',)