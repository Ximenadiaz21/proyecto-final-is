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

    # CU-17: Registro y edición de libro con autor principal y múltiples coautores (libro_autor)
    def test_cu17_libro_con_multiples_autores(self):
        coautor = Autor.objects.create(nombre='Steven', apellidos='Morris')
        self.client.force_login(self.bibliotecario)

        self.client.post(reverse('nuevo_libro'), {
            'isbn': '9786071500099',
            'titulo': 'Bases de Datos Avanzadas',
            'editorial': self.editorial.id,
            'categoria': self.categoria.id,
            'idioma': 'Español',
            'costo_reposicion': '450.00',
            'autor': self.autor.id,
            'coautores': [coautor.id],
        })

        creado = Libro.objects.get(isbn='9786071500099')
        relaciones = list(LibroAutor.objects.filter(libro=creado).order_by('orden'))
        self.assertEqual(len(relaciones), 2)
        self.assertEqual(relaciones[0].autor_id, self.autor.id)
        self.assertEqual(relaciones[0].orden, 1)
        self.assertEqual(relaciones[1].autor_id, coautor.id)
        self.assertEqual(relaciones[1].orden, 2)

    # CU-19 y RF-10: Baja de autor/editorial/categoría protegida si tiene libros y permitida si está libre
    def test_cu19_eliminar_catalogo_protegido_y_libre(self):
        autor_libre = Autor.objects.create(nombre='Autor', apellidos='Sin Libros')
        editorial_libre = Editorial.objects.create(nombre='Editorial Libre')
        categoria_libre = Categoria.objects.create(nombre='Categoría Libre')

        self.client.force_login(self.bibliotecario)

        # Con libros asociados se protege por integridad referencial (ON DELETE PROTECT)
        self.client.post(reverse('eliminar_autor', args=[self.autor.id]))
        self.client.post(reverse('eliminar_editorial', args=[self.editorial.id]))
        self.client.post(reverse('eliminar_categoria', args=[self.categoria.id]))
        self.assertTrue(Autor.objects.filter(id=self.autor.id).exists())
        self.assertTrue(Editorial.objects.filter(id=self.editorial.id).exists())
        self.assertTrue(Categoria.objects.filter(id=self.categoria.id).exists())

        # Sin libros asociados se dan de baja correctamente
        self.client.post(reverse('eliminar_autor', args=[autor_libre.id]))
        self.client.post(reverse('eliminar_editorial', args=[editorial_libre.id]))
        self.client.post(reverse('eliminar_categoria', args=[categoria_libre.id]))
        self.assertFalse(Autor.objects.filter(id=autor_libre.id).exists())
        self.assertFalse(Editorial.objects.filter(id=editorial_libre.id).exists())
        self.assertFalse(Categoria.objects.filter(id=categoria_libre.id).exists())

    # RN-12: Editar un ejemplar de EN_REPARACION a DISPONIBLE (o dar de alta uno nuevo) respeta la cola FIFO
    def test_rn12_ejemplar_form_asigna_cola_fifo_al_pasar_a_disponible(self):
        from prestamos.models import PoliticaPrestamo, Reserva

        PoliticaPrestamo.objects.update_or_create(
            tipo_usuario='ESTUDIANTE',
            defaults={
                'dias_prestamo': 7,
                'max_libros': 3,
                'max_renovaciones': 1,
                'multa_por_dia': Decimal('10.00'),
                'multa_maxima': Decimal('300.00'),
                'horas_para_recoger': 48,
            },
        )

        ejemplar_reparacion = Ejemplar.objects.create(
            libro=self.libro,
            codigo_inventario='EJ-REP-01',
            estado='EN_REPARACION',
        )
        reserva = Reserva.objects.create(
            usuario=self.estudiante,
            libro=self.libro,
            estado='PENDIENTE',
        )

        form = EjemplarForm(
            {
                'codigo_inventario': ejemplar_reparacion.codigo_inventario,
                'ubicacion': 'Estante B',
                'estado': 'DISPONIBLE',
                'observaciones': 'Reparado',
            },
            instance=ejemplar_reparacion,
        )
        self.assertTrue(form.is_valid())
        form.save()

        ejemplar_reparacion.refresh_from_db()
        reserva.refresh_from_db()
        self.assertEqual(ejemplar_reparacion.estado, 'RESERVADO')
        self.assertEqual(reserva.estado, 'DISPONIBLE')
        self.assertEqual(reserva.ejemplar_asignado_id, ejemplar_reparacion.id)
        self.assertEqual(len(form.reservas_asignadas), 1)

    # CU-17: No permite dar de baja lógica un libro con préstamos en curso o reservas activas (y exige POST)
    def test_cu17_no_baja_logica_libro_con_prestamo_o_reserva_y_exige_post(self):
        from prestamos.models import Prestamo, Reserva

        self.client.force_login(self.bibliotecario)

        # GET no debe permitirse (405 Method Not Allowed)
        self.assertEqual(
            self.client.get(reverse('cambiar_estado_libro', args=[self.libro.id])).status_code,
            405,
        )

        # Con préstamo SOLICITADO o ACTIVO no permite baja
        ej = Ejemplar.objects.get(codigo_inventario='EJ-CAT-01')
        prestamo = Prestamo.objects.create(usuario=self.estudiante, ejemplar=ej, estado='SOLICITADO')
        self.client.post(reverse('cambiar_estado_libro', args=[self.libro.id]))
        self.libro.refresh_from_db()
        self.assertTrue(self.libro.activo)

        prestamo.estado = 'DEVUELTO'
        prestamo.save()

        # Con reserva PENDIENTE tampoco permite baja
        reserva = Reserva.objects.create(usuario=self.estudiante, libro=self.libro, estado='PENDIENTE')
        self.client.post(reverse('cambiar_estado_libro', args=[self.libro.id]))
        self.libro.refresh_from_db()
        self.assertTrue(self.libro.activo)

        reserva.estado = 'CANCELADA'
        reserva.save()

        # Ya sin préstamos ni reservas activas sí permite baja
        self.client.post(reverse('cambiar_estado_libro', args=[self.libro.id]))
        self.libro.refresh_from_db()
        self.assertFalse(self.libro.activo)

    # Esquema BD: el modelo Libro valida el formato de ISBN (10 o 13 dígitos sin guiones) incluso fuera de formularios
    def test_modelo_libro_valida_formato_isbn(self):
        from django.core.exceptions import ValidationError

        libro_invalido = Libro(
            isbn='ISBN-MALO',
            titulo='Libro con ISBN inválido',
            editorial=self.editorial,
            categoria=self.categoria,
            costo_reposicion=Decimal('100.00'),
        )
        with self.assertRaises(ValidationError):
            libro_invalido.full_clean()



