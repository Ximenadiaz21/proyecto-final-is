from django.contrib import admin
from .models import Autor, Categoria, Editorial, Libro, LibroAutor, Ejemplar


@admin.register(Autor)
class AutorAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'apellidos', 'nacionalidad')
    search_fields = ('nombre', 'apellidos')
    ordering = ('apellidos', 'nombre')


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'descripcion')
    search_fields = ('nombre',)
    ordering = ('nombre',)


@admin.register(Editorial)
class EditorialAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'pais')
    search_fields = ('nombre',)
    ordering = ('nombre',)


@admin.register(Libro)
class LibroAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titulo', 'isbn', 'editorial_nombre', 'categoria_nombre',
        'anio_publicacion', 'activo',
    )
    list_display_links = ('id', 'titulo')
    list_filter = ('activo', 'categoria')
    search_fields = ('titulo', 'isbn')
    ordering = ('titulo',)
    list_select_related = ('editorial', 'categoria')

    @admin.display(description='Editorial', ordering='editorial__nombre')
    def editorial_nombre(self, obj):
        return obj.editorial.nombre

    @admin.display(description='Categoría', ordering='categoria__nombre')
    def categoria_nombre(self, obj):
        return obj.categoria.nombre


@admin.register(LibroAutor)
class LibroAutorAdmin(admin.ModelAdmin):
    list_display = ('id', 'libro_titulo', 'autor_nombre', 'orden')
    search_fields = ('libro__titulo', 'autor__nombre', 'autor__apellidos')
    list_select_related = ('libro', 'autor')

    @admin.display(description='Libro', ordering='libro__titulo')
    def libro_titulo(self, obj):
        return obj.libro.titulo

    @admin.display(description='Autor')
    def autor_nombre(self, obj):
        return f"{obj.autor.nombre} {obj.autor.apellidos}"


@admin.register(Ejemplar)
class EjemplarAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'codigo_inventario', 'libro_titulo', 'ubicacion',
        'estado', 'fecha_adquisicion',
    )
    list_display_links = ('id', 'codigo_inventario')

    # Permite cambiar el estado del ejemplar directo desde la lista
    list_editable = ('estado',)

    list_filter = ('estado',)
    search_fields = ('codigo_inventario', 'libro__titulo')
    ordering = ('codigo_inventario',)
    list_select_related = ('libro',)

    @admin.display(description='Libro', ordering='libro__titulo')
    def libro_titulo(self, obj):
        return obj.libro.titulo