from django.contrib import admin
from .models import Usuario, Estudiante, Profesor, Carrera, Departamento

admin.site.register(Usuario)
admin.site.register(Estudiante)
admin.site.register(Profesor)
admin.site.register(Carrera)
admin.site.register(Departamento)