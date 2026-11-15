from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from cuentas.models import Usuario
from .forms_ejemplares import EjemplarForm
from .models import Autor, Categoria, Editorial, Ejemplar, Libro, LibroAutor


# Pruebas de búsqueda en el catálogo y administración del acervo (CU-04, CU-17, CU-18, RF-02, RF-10)
class CatalogoTests(TestCase):

    def setUp(self):
        self.estudiante = Usuario.objects.create_user(
            username='alumno_cat',
            password='password123',
            email='alumno_cat@test.mx',
            tipo_usuario='ESTUDIANTE',
        )
        self.bibliotecario = Usuario.objects.create_user(
            username='biblio_cat',
            password='password123',
            email='biblio_cat@test.mx',
            tipo_usuario='BIBLIOTECARIO',
        )

        self.editorial = Editorial.objects.create(nombre='Alfaomega', pais='México')
        self.categoria = Categoria.objects.create(nombre='Base de Datos')
        self.autor = Autor.objects.create(nombre='Carlos', apellidos='Coronel')

        self.libro = Libro.objects.create(
            isbn='9786071500001',
            titulo='Diseño de Bases de Datos',
            editorial=self.editorial,
            categoria=self.categoria,
            costo_reposicion=Decimal('380.00'),
            activo=True,
        )
        LibroAutor.objects.create(libro=self.libro, autor=self.autor, orden=1)

        Ejemplar.objects.create(
            libro=self.libro,
            codigo_inventario='EJ-CAT-01',
            estado='DISPONIBLE',
        )
        Ejemplar.objects.create(
            libro=self.libro,
            codigo_inventario='EJ-CAT-02',
            estado='PRESTADO',
        )

    # RF-02 y CU-04: Búsqueda por título, autor e ISBN y conteo de disponibles
    def test_busqueda_catalogo_y_disponibilidad(self):
        self.client.force_login(self.estudiante)

        respuesta = self.client.get(reverse('lista_libros'), {'q': 'Coronel'})
        self.assertEqual(respuesta.status_code, 200)
        libros = list(respuesta.context['libros'])
        self.assertEqual(len(libros), 1)
        self.assertEqual(libros[0].id, self.libro.id)
        self.assertEqual(libros[0].disponibles, 1)

    # CU-17 y RF-10: Baja lógica oculta el libro del catálogo para lectores
    def test_baja_logica_libro(self):
        self.client.force_login(self.bibliotecario)
        self.client.post(reverse('cambiar_estado_libro', args=[self.libro.id]))

        self.libro.refresh_from_db()
        self.assertFalse(self.libro.activo)

        self.client.force_login(self.estudiante)
        respuesta = self.client.get(reverse('lista_libros'))
        self.assertEqual(len(respuesta.context['libros']), 0)

    # CU-18: Alta de varios ejemplares con generación automática de código
    def test_alta_multiple_ejemplares(self):
        form = EjemplarForm({
            'isbn': self.libro.isbn,
            'cantidad': 2,
            'codigo_inventario': '',
            'ubicacion': 'Estante A',
            'estado': 'DISPONIBLE',
        })
        self.assertTrue(form.is_valid())
        creados = form.save()
        self.assertEqual(len(creados), 2)
        self.assertEqual(Ejemplar.objects.filter(libro=self.libro).count(), 4)

