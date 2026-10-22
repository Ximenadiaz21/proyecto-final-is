from django.db import models

# Create your models here.
class Autor(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    nacionalidad = models.CharField(max_length=60, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'autor'

class Categoria(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=100)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'categoria'

class Editorial(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=150)
    pais = models.CharField(max_length=60, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'editorial'

class Libro(models.Model):
    id = models.BigAutoField(primary_key=True)
    isbn = models.CharField(unique=True, max_length=13)
    titulo = models.CharField(max_length=255)
    subtitulo = models.CharField(max_length=255, blank=True, null=True)
    editorial = models.ForeignKey(Editorial, models.DO_NOTHING)
    categoria = models.ForeignKey(Categoria, models.DO_NOTHING)
    anio_publicacion = models.PositiveSmallIntegerField(blank=True, null=True)
    edicion = models.CharField(max_length=30, blank=True, null=True)
    idioma = models.CharField(max_length=30)
    num_paginas = models.PositiveSmallIntegerField(blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    portada = models.CharField(max_length=255, blank=True, null=True)
    costo_reposicion = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'libro'
        db_table_comment = 'TÝtulo u obra; los objetos fÝsicos estßn en ejemplar'

class LibroAutor(models.Model):
    id = models.BigAutoField(primary_key=True)
    libro = models.ForeignKey(Libro, models.DO_NOTHING)
    autor = models.ForeignKey(Autor, models.DO_NOTHING)
    orden = models.PositiveIntegerField()

    class Meta:
        managed = False
        db_table = 'libro_autor'
        unique_together = (('libro', 'autor'),)
        db_table_comment = 'Relaci¾n muchos a muchos entre libro y autor'

class Ejemplar(models.Model):
    id = models.BigAutoField(primary_key=True)
    libro = models.ForeignKey('Libro', models.DO_NOTHING)
    codigo_inventario = models.CharField(unique=True, max_length=30)
    ubicacion = models.CharField(max_length=50, blank=True, null=True)
    estado = models.CharField(max_length=15)
    fecha_adquisicion = models.DateField(blank=True, null=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ejemplar'
        db_table_comment = 'Copia fÝsica de un libro'
