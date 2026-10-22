
from django.contrib import admin
from .models import Autor, Categoria, Editorial, Libro, Ejemplar

admin.site.register(Autor)
admin.site.register(Categoria)
admin.site.register(Editorial)
admin.site.register(Libro)
admin.site.register(Ejemplar)