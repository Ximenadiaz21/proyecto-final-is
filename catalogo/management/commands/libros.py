import json
import random
import time
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from django.core.management.base import BaseCommand
from django.db import transaction

from catalogo.models import (
    Autor, Editorial, Categoria, Libro, LibroAutor, Ejemplar
)


# Libros reales que utilizaremos como catálogo de demostración
# Cada categoría contiene cinco obras de diferentes autores
LIBROS = {
    'Programación': [
        ('Clean Code', 'Robert C. Martin'),
        ('The Pragmatic Programmer', 'Andrew Hunt'),
        ('Introduction to Algorithms', 'Thomas H. Cormen'),
        ('Design Patterns', 'Erich Gamma'),
        ('Code Complete', 'Steve McConnell'),
    ],
    'Ciencia de datos e inteligencia artificial': [
        ('Python for Data Analysis', 'Wes McKinney'),
        ('Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow', 'Aurélien Géron'),
        ('Deep Learning', 'Ian Goodfellow'),
        ('The Elements of Statistical Learning', 'Trevor Hastie'),
        ('Data Science from Scratch', 'Joel Grus'),
    ],
    'Matemáticas': [
        ('Calculus', 'James Stewart'),
        ('Linear Algebra and Its Applications', 'David C. Lay'),
        ('Discrete Mathematics and Its Applications', 'Kenneth H. Rosen'),
        ('How to Prove It', 'Daniel J. Velleman'),
        ('Introduction to Probability', 'Joseph K. Blitzstein'),
    ],
    'Física': [
        ('A Brief History of Time', 'Stephen Hawking'),
        ('The Feynman Lectures on Physics', 'Richard P. Feynman'),
        ('Six Easy Pieces', 'Richard P. Feynman'),
        ('The Elegant Universe', 'Brian Greene'),
        ('The Fabric of the Cosmos', 'Brian Greene'),
    ],
    'Literatura clásica': [
        ('Pride and Prejudice', 'Jane Austen'),
        ('Frankenstein', 'Mary Shelley'),
        ('1984', 'George Orwell'),
        ('Brave New World', 'Aldous Huxley'),
        ('The Great Gatsby', 'F. Scott Fitzgerald'),
    ],
    'Literatura latinoamericana': [
        ('Cien años de soledad', 'Gabriel García Márquez'),
        ('Pedro Páramo', 'Juan Rulfo'),
        ('La casa de los espíritus', 'Isabel Allende'),
        ('Rayuela', 'Julio Cortázar'),
        ('Como agua para chocolate', 'Laura Esquivel'),
    ],
    'Fantasía y ciencia ficción': [
        ('Dune', 'Frank Herbert'),
        ('The Hobbit', 'J. R. R. Tolkien'),
        ("Harry Potter and the Philosopher's Stone", 'J. K. Rowling'),
        ('The Hunger Games', 'Suzanne Collins'),
        ('Foundation', 'Isaac Asimov'),
    ],
    'Psicología': [
        ('Thinking, Fast and Slow', 'Daniel Kahneman'),
        ("The Psychology of Money", "Morgan Housel"),
        ('Influence', 'Robert B. Cialdini'),
        ('The Power of Habit', 'Charles Duhigg'),
        ('Emotional Intelligence', 'Daniel Goleman'),
    ],
    'Historia': [
        ('Sapiens', 'Yuval Noah Harari'),
        ('Guns, Germs, and Steel', 'Jared Diamond'),
        ("A People's History of the United States", 'Howard Zinn'),
        ('The Diary of a Young Girl', 'Anne Frank'),
        ('The Silk Roads', 'Peter Frankopan'),
    ],
    'Negocios y administración': [
        ('The Lean Startup', 'Eric Ries'),
        ('Zero to One', 'Peter Thiel'),
        ('Good to Great', 'Jim Collins'),
        ('The Intelligent Investor', 'Benjamin Graham'),
        ('Start with Why', 'Simon Sinek'),
    ],
}


def costo_aleatorio():
    # Costo de reposición de demostración: entre $150 y $900 MXN (RN-13)
    return Decimal(random.randrange(150, 901, 10))


def normalizar(texto):
    # Quita diferencias de acentos, mayúsculas y puntuación
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ''.join(c.lower() for c in texto if c.isalnum())


def isbn_valido(isbn):
    # Comprueba que el ISBN-13 tenga su dígito de control correcto
    if len(isbn) != 13 or not isbn.isdigit():
        return False

    suma = sum(
        int(digito) * (1 if i % 2 == 0 else 3)
        for i, digito in enumerate(isbn[:12])
    )

    return (10 - suma % 10) % 10 == int(isbn[-1])


def isbn_respaldo(semilla):
    # Genera un ISBN-13 con dígito de control válido cuando no hay respuesta de red
    base = f'9786070{semilla:05d}'
    suma = sum(
        int(digito) * (1 if i % 2 == 0 else 3)
        for i, digito in enumerate(base)
    )
    control = (10 - suma % 10) % 10
    return f'{base}{control}'


def datos_respaldo(indice):
    # Datos locales para completar el catálogo si Open Library no responde
    semilla = indice
    isbn = isbn_respaldo(semilla)
    while Libro.objects.filter(isbn=isbn).exists():
        semilla += 1
        isbn = isbn_respaldo(semilla)

    return {
        'isbn': isbn,
        'editorial': 'Editorial Universitaria',
        'anio': 2020,
        'portada': None,
    }


def buscar_libro(titulo, autor):
    # Consulta el catálogo de Open Library para obtener datos reales
    parametros = urlencode({
        'title': titulo,
        'author': autor,
        'fields': 'title,author_name,isbn,publisher,first_publish_year,cover_i',
        'limit': 10,
    })

    url = f'https://openlibrary.org/search.json?{parametros}'

    solicitud = Request(
        url,
        headers={'User-Agent': 'BibliotecaEscolarDemo/1.0'}
    )

    try:
        with urlopen(solicitud, timeout=8) as respuesta:
            datos = json.load(respuesta)

    except (HTTPError, URLError, TimeoutError, ValueError):
        return None

    # Verifica que el resultado corresponda al título y al autor
    for resultado in datos.get('docs', []):
        titulo_encontrado = resultado.get('title', '')
        autores_encontrados = resultado.get('author_name', [])

        similitud = SequenceMatcher(
            None,
            normalizar(titulo),
            normalizar(titulo_encontrado)
        ).ratio()

        apellido = normalizar(autor.split()[-1])

        autor_correcto = any(
            apellido in normalizar(nombre)
            for nombre in autores_encontrados
        )

        if similitud < 0.85 or not autor_correcto:
            continue

        # Selecciona un ISBN-13 válido registrado para la obra
        isbns = [
            isbn for isbn in resultado.get('isbn', [])
            if isbn_valido(isbn)
        ]

        editoriales = resultado.get('publisher', [])

        if not isbns or not editoriales:
            continue

        portada_id = resultado.get('cover_i')

        return {
            'isbn': sorted(isbns)[0],
            'editorial': editoriales[0][:150],
            'anio': resultado.get('first_publish_year'),
            'portada': (
                f'https://covers.openlibrary.org/b/id/{portada_id}-M.jpg'
                if portada_id else None
            ),
        }

    return None


class Command(BaseCommand):
    help = 'Carga libros reales y ejemplares de demostración'

    def add_arguments(self, parser):
        parser.add_argument(
            '--offline',
            action='store_true',
            help='Carga los libros con datos locales sin consultar Open Library.',
        )

    def handle(self, *args, **options):

        registrados = 0
        respaldo_usado = 0
        fallos_seguidos = 0
        modo_offline = options['offline']
        indice = 1

        # Recorre las categorías y los libros definidos anteriormente
        for categoria_nombre, obras in LIBROS.items():

            categoria, _ = Categoria.objects.get_or_create(
                nombre=categoria_nombre,
                defaults={
                    'descripcion': f'Libros de {categoria_nombre}'
                }
            )

            for titulo, nombre_autor in obras:
                indice_actual = indice
                indice += 1

                # No duplica títulos que ya fueron cargados
                existente = Libro.objects.filter(
                    titulo=titulo,
                    categoria=categoria
                ).first()

                if existente:
                    campos_actualizar = []
                    if existente.costo_reposicion == 0:
                        existente.costo_reposicion = costo_aleatorio()
                        campos_actualizar.append('costo_reposicion')
                    if existente.idioma == 'No especificado':
                        existente.idioma = 'Español'
                        campos_actualizar.append('idioma')
                    if campos_actualizar:
                        existente.save(update_fields=campos_actualizar)
                    self.crear_ejemplares(existente)
                    registrados += 1
                    continue

                datos = None
                if not modo_offline and fallos_seguidos < 2:
                    datos = buscar_libro(titulo, nombre_autor)
                    if datos is None:
                        fallos_seguidos += 1
                    else:
                        fallos_seguidos = 0
                    time.sleep(1.1)

                # Si no hubo respuesta o el ISBN ya está ocupado, usa datos locales de respaldo
                if datos is None or Libro.objects.filter(isbn=datos['isbn']).exists():
                    datos = datos_respaldo(indice_actual)
                    respaldo_usado += 1

                with transaction.atomic():

                    editorial, _ = Editorial.objects.get_or_create(
                        nombre=datos['editorial']
                    )

                    partes = nombre_autor.split()

                    autor, _ = Autor.objects.get_or_create(
                        nombre=' '.join(partes[:-1]),
                        apellidos=partes[-1]
                    )

                    # Registra la obra utilizando los datos consultados o de respaldo
                    libro = Libro.objects.create(
                        isbn=datos['isbn'],
                        titulo=titulo,
                        editorial=editorial,
                        categoria=categoria,
                        anio_publicacion=datos['anio'],
                        idioma='Español',
                        portada=datos['portada'],
                        descripcion=(
                            f'Obra de {nombre_autor}. '
                            'Registro bibliográfico de demostración.'
                        ),
                        costo_reposicion=costo_aleatorio(),
                        activo=True,
                    )

                    LibroAutor.objects.get_or_create(
                        libro=libro,
                        autor=autor,
                        defaults={'orden': 1}
                    )

                    # Crea dos ejemplares físicos ficticios por título
                    self.crear_ejemplares(libro)

                registrados += 1
                self.stdout.write(f'Registrado: {titulo}')

        self.stdout.write(self.style.SUCCESS(
            f'Obras del listado registradas o existentes: {registrados}'
        ))

        self.stdout.write(
            f'Total de libros en MySQL: {Libro.objects.count()}'
        )

        self.stdout.write(
            f'Total de ejemplares en MySQL: {Ejemplar.objects.count()}'
        )

        if respaldo_usado:
            self.stdout.write(
                f'Obras completadas con datos locales: {respaldo_usado}'
            )

    def crear_ejemplares(self, libro):

        # Los códigos de inventario son internos de nuestra biblioteca
        # No representan ejemplares físicos reales
        for numero in range(1, 3):

            Ejemplar.objects.get_or_create(
                codigo_inventario=f'DEMO-{libro.id:05d}-{numero}',
                defaults={
                    'libro': libro,
                    'ubicacion': f'Estante {((libro.id - 1) % 10) + 1}',
                    'estado': 'DISPONIBLE',
                }
            )