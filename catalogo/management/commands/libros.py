
import json
import time
import unicodedata
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
        with urlopen(solicitud, timeout=20) as respuesta:
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

    def handle(self, *args, **options):

        registrados = 0
        pendientes = []

        # Recorre las categorías y los libros definidos anteriormente
        for categoria_nombre, obras in LIBROS.items():

            categoria, _ = Categoria.objects.get_or_create(
                nombre=categoria_nombre,
                defaults={
                    'descripcion': f'Libros de {categoria_nombre}'
                }
            )

            for titulo, nombre_autor in obras:

                # No duplica títulos que ya fueron cargados
                existente = Libro.objects.filter(
                    titulo=titulo,
                    categoria=categoria
                ).first()

                if existente:
                    self.crear_ejemplares(existente)
                    registrados += 1
                    continue

                datos = buscar_libro(titulo, nombre_autor)

                # Evita inventar ISBN o editoriales cuando faltan datos
                if datos is None:
                    pendientes.append(titulo)
                    self.stdout.write(
                        self.style.WARNING(f'Sin verificar: {titulo}')
                    )
                    time.sleep(1.1)
                    continue

                if Libro.objects.filter(isbn=datos['isbn']).exists():
                    pendientes.append(titulo)
                    time.sleep(1.1)
                    continue

                with transaction.atomic():

                    editorial, _ = Editorial.objects.get_or_create(
                        nombre=datos['editorial']
                    )

                    partes = nombre_autor.split()

                    autor, _ = Autor.objects.get_or_create(
                        nombre=' '.join(partes[:-1]),
                        apellidos=partes[-1]
                    )

                    # Registra la obra utilizando los datos consultados
                    libro = Libro.objects.create(
                        isbn=datos['isbn'],
                        titulo=titulo,
                        editorial=editorial,
                        categoria=categoria,
                        anio_publicacion=datos['anio'],
                        idioma='No especificado',
                        portada=datos['portada'],
                        descripcion=(
                            f'Obra de {nombre_autor}. '
                            'Registro bibliográfico de demostración.'
                        ),
                        costo_reposicion=0,
                        activo=1,
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

                # Espacia las consultas para respetar el servicio externo
                time.sleep(1.1)

        self.stdout.write(self.style.SUCCESS(
            f'Obras del listado registradas o existentes: {registrados}'
        ))

        self.stdout.write(
            f'Total de libros en MySQL: {Libro.objects.count()}'
        )

        self.stdout.write(
            f'Total de ejemplares en MySQL: {Ejemplar.objects.count()}'
        )

        if pendientes:
            self.stdout.write(self.style.WARNING(
                f'Obras pendientes de verificar: {len(pendientes)}'
            ))

            for titulo in pendientes:
                self.stdout.write(f'  - {titulo}')

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
