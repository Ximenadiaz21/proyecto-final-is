from django.db import models


class Autor(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    nacionalidad = models.CharField(max_length=60, blank=True, null=True)

    class Meta:
        db_table = 'autor'

    def __str__(self):
        return f"{self.nombre} {self.apellidos}"


class Categoria(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=100)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'categoria'

    def __str__(self):
        return self.nombre


class Editorial(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=150)
    pais = models.CharField(max_length=60, blank=True, null=True)

    class Meta:
        db_table = 'editorial'

    def __str__(self):
        return self.nombre


class Libro(models.Model):
    id = models.BigAutoField(primary_key=True)
    isbn = models.CharField(unique=True, max_length=13)
    titulo = models.CharField(max_length=255, db_index=True)
    subtitulo = models.CharField(max_length=255, blank=True, null=True)
    editorial = models.ForeignKey(Editorial, models.PROTECT)
    categoria = models.ForeignKey(Categoria, models.PROTECT)
    anio_publicacion = models.PositiveSmallIntegerField(blank=True, null=True)
    edicion = models.CharField(max_length=30, blank=True, null=True)
    idioma = models.CharField(max_length=30, default='Español')
    num_paginas = models.PositiveSmallIntegerField(blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    portada = models.CharField(max_length=255, blank=True, null=True)
    costo_reposicion = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'libro'
        db_table_comment = 'Título u obra; los objetos físicos están en ejemplar'

    def __str__(self):
        return self.titulo


class LibroAutor(models.Model):
    id = models.BigAutoField(primary_key=True)
    libro = models.ForeignKey(Libro, models.CASCADE)
    autor = models.ForeignKey(Autor, models.PROTECT)
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'libro_autor'
        unique_together = (('libro', 'autor'),)
        db_table_comment = 'Relación muchos a muchos entre libro y autor'


class Ejemplar(models.Model):
    ESTADOS = [
        ('DISPONIBLE', 'Disponible'),
        ('RESERVADO', 'Reservado'),
        ('PRESTADO', 'Prestado'),
        ('EN_REPARACION', 'En reparación'),
        ('PERDIDO', 'Perdido'),
        ('BAJA', 'Baja'),
    ]

    id = models.BigAutoField(primary_key=True)
    libro = models.ForeignKey('Libro', models.PROTECT)
    codigo_inventario = models.CharField(unique=True, max_length=30)
    ubicacion = models.CharField(max_length=50, blank=True, null=True)
    estado = models.CharField(max_length=15, choices=ESTADOS, default='DISPONIBLE', db_index=True)
    fecha_adquisicion = models.DateField(blank=True, null=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ejemplar'
        db_table_comment = 'Copia física de un libro'

    def __str__(self):
        return self.codigo_inventario