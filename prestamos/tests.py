from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Autor, Categoria, Editorial, Ejemplar, Libro
from cuentas.models import Notificacion, Usuario
from multas.models import Multa
from .models import PoliticaPrestamo, Prestamo, Reserva
from .reglas import liberar_o_asignar_ejemplar, motivo_inelegible, motivo_no_renovable


# Pruebas unitarias de las reglas de negocio RN-01 a RN-12 y RN-15 (RNF-07)
class ReglasNegocioPrestamosTests(TestCase):

    # Configura los datos base para las pruebas (usuarios, políticas, catálogo y ejemplares)
    def setUp(self):
        # Asegura que existan las políticas de préstamo con los valores por defecto (RN-01 a RN-06)
        self.politica_estudiante, _ = PoliticaPrestamo.objects.update_or_create(
            tipo_usuario='ESTUDIANTE',
            defaults={
                'dias_prestamo': 7,
                'max_libros': 3,
                'max_renovaciones': 1,
                'multa_por_dia': Decimal('10.00'),
                'multa_maxima': Decimal('300.00'),
                'horas_para_recoger': 48,
            }
        )
        self.politica_profesor, _ = PoliticaPrestamo.objects.update_or_create(
            tipo_usuario='PROFESOR',
            defaults={
                'dias_prestamo': 30,
                'max_libros': 10,
                'max_renovaciones': 2,
                'multa_por_dia': Decimal('10.00'),
                'multa_maxima': Decimal('300.00'),
                'horas_para_recoger': 48,
            }
        )

        # Crea usuarios de prueba para cada actor del sistema
        self.estudiante = Usuario.objects.create_user(
            username='estudiante_test',
            password='password123',
            email='estudiante@test.mx',
            tipo_usuario='ESTUDIANTE',
        )
        self.estudiante_dos = Usuario.objects.create_user(
            username='estudiante2_test',
            password='password123',
            email='estudiante2@test.mx',
            tipo_usuario='ESTUDIANTE',
        )
        self.profesor = Usuario.objects.create_user(
            username='profesor_test',
            password='password123',
            email='profesor@test.mx',
            tipo_usuario='PROFESOR',
        )
        self.bibliotecario = Usuario.objects.create_user(
            username='biblio_test',
            password='password123',
            email='biblio@test.mx',
            tipo_usuario='BIBLIOTECARIO',
        )

        # Crea datos bibliográficos base (editorial, categoría, autor y 4 libros con ejemplares)
        self.editorial = Editorial.objects.create(nombre='Editorial Universitaria', pais='México')
        self.categoria = Categoria.objects.create(nombre='Ingeniería de Software')
        self.autor = Autor.objects.create(nombre='Ian', apellidos='Sommerville')

        self.libros = []
        self.ejemplares = []
        for i in range(1, 5):
            libro = Libro.objects.create(
                isbn=f'978000000000{i}',
                titulo=f'Libro de Prueba {i}',
                editorial=self.editorial,
                categoria=self.categoria,
                costo_reposicion=Decimal('250.00'),
                activo=True,
            )
            ejemplar = Ejemplar.objects.create(
                libro=libro,
                codigo_inventario=f'INV-TEST-0{i}',
                estado='DISPONIBLE',
            )
            self.libros.append(libro)
            self.ejemplares.append(ejemplar)

    # RN-01 y RN-06: Verifica el plazo de 48h al solicitar y los días de préstamo por rol al entregar
    def test_rn01_y_rn06_dias_prestamo_y_horas_para_recoger(self):
        # El estudiante solicita el libro 1
        self.client.force_login(self.estudiante)
        self.client.post(reverse('solicitar_prestamo', args=[self.libros[0].id]))

        prestamo_est = Prestamo.objects.get(usuario=self.estudiante, ejemplar=self.ejemplares[0])
        self.assertEqual(prestamo_est.estado, 'SOLICITADO')

        # RN-06: La fecha límite para recoger debe ser ~48 horas después de la solicitud
        diferencia_horas = (prestamo_est.fecha_limite_recoger - prestamo_est.fecha_solicitud).total_seconds() / 3600
        self.assertAlmostEqual(diferencia_horas, 48, places=1)

        # El bibliotecario entrega el libro al estudiante (CU-23)
        self.client.force_login(self.bibliotecario)
        self.client.post(reverse('entregar_prestamo', args=[prestamo_est.id]))
        prestamo_est.refresh_from_db()

        # RN-01: Estudiante recibe 7 días naturales de préstamo
        self.assertEqual(prestamo_est.estado, 'ACTIVO')
        self.assertEqual(prestamo_est.fecha_vencimiento, timezone.localdate() + timedelta(days=7))

        # El bibliotecario registra préstamo en mostrador para el profesor (CU-24)
        self.client.post(reverse('registrar_prestamo_mostrador'), {
            'username': self.profesor.username,
            'codigo_inventario': self.ejemplares[1].codigo_inventario,
        })
        prestamo_prof = Prestamo.objects.get(usuario=self.profesor, ejemplar=self.ejemplares[1])

        # RN-01: Profesor recibe 30 días naturales de préstamo
        self.assertEqual(prestamo_prof.estado, 'ACTIVO')
        self.assertEqual(prestamo_prof.fecha_vencimiento, timezone.localdate() + timedelta(days=30))

    # RN-02: Verifica que un estudiante no pueda superar el máximo de 3 libros simultáneos
    def test_rn02_limite_maximo_libros_simultaneos(self):
        self.client.force_login(self.estudiante)

        # Solicita 3 libros distintos (el máximo permitido para estudiante)
        for i in range(3):
            self.client.post(reverse('solicitar_prestamo', args=[self.libros[i].id]))

        self.assertEqual(Prestamo.objects.filter(usuario=self.estudiante).count(), 3)

        # Intenta solicitar un 4.º libro y verifica que sea rechazado
        self.client.post(reverse('solicitar_prestamo', args=[self.libros[3].id]))
        self.assertEqual(Prestamo.objects.filter(usuario=self.estudiante).count(), 3)
        self.ejemplares[3].refresh_from_db()
        self.assertEqual(self.ejemplares[3].estado, 'DISPONIBLE')

    # RN-04, RN-05 y RN-07: Verifica cálculo de multa con casos límite (0, 1, varios días y tope máximo)
    def test_rn04_rn05_rn07_calculo_multa_casos_limite(self):
        hoy = timezone.localdate()
        prestamo = Prestamo.objects.create(
            usuario=self.estudiante,
            ejemplar=self.ejemplares[0],
            estado='ACTIVO',
            fecha_vencimiento=hoy,
        )

        # Caso límite 1: 0 días de retraso (devuelto el día de vencimiento) -> $0.00
        self.assertEqual(prestamo.dias_retraso(hoy), 0)
        self.assertEqual(prestamo.calcular_multa(self.politica_estudiante, hoy), Decimal('0.00'))

        # Caso límite 2: 1 día de retraso -> $10.00 MXN (RN-04)
        un_dia_despues = hoy + timedelta(days=1)
        self.assertEqual(prestamo.dias_retraso(un_dia_despues), 1)
        self.assertEqual(prestamo.calcular_multa(self.politica_estudiante, un_dia_despues), Decimal('10.00'))

        # Caso 3: 5 días de retraso -> $50.00 MXN
        cinco_dias = hoy + timedelta(days=5)
        self.assertEqual(prestamo.dias_retraso(cinco_dias), 5)
        self.assertEqual(prestamo.calcular_multa(self.politica_estudiante, cinco_dias), Decimal('50.00'))

        # Caso límite 4: 45 días de retraso -> aplica tope máximo de $300.00 MXN (RN-05)
        cuarenta_y_cinco_dias = hoy + timedelta(days=45)
        self.assertEqual(prestamo.dias_retraso(cuarenta_y_cinco_dias), 45)
        self.assertEqual(prestamo.calcular_multa(self.politica_estudiante, cuarenta_y_cinco_dias), Decimal('300.00'))

    # RN-08: Verifica que un usuario con multas pendientes o préstamos vencidos sea inelegible
    def test_rn08_bloqueo_por_multa_pendiente_o_prestamo_vencido(self):
        # Inicialmente el estudiante es elegible
        self.assertEqual(motivo_inelegible(self.estudiante), '')

        # Crea un préstamo vencido para el estudiante
        prestamo = Prestamo.objects.create(
            usuario=self.estudiante,
            ejemplar=self.ejemplares[0],
            estado='VENCIDO',
            fecha_vencimiento=timezone.localdate() - timedelta(days=2),
        )
        self.assertIn('vencidos', motivo_inelegible(self.estudiante))

        # Marca el préstamo como devuelto pero le registra una multa PENDIENTE
        prestamo.estado = 'DEVUELTO'
        prestamo.save()
        Multa.objects.create(
            prestamo=prestamo,
            usuario=self.estudiante,
            motivo='RETRASO',
            dias_retraso=2,
            monto=Decimal('20.00'),
            estado='PENDIENTE',
        )
        self.assertIn('multas pendientes', motivo_inelegible(self.estudiante))

    # RN-03, RN-09 y RN-10: Verifica renovación de préstamo, extensión de fecha y restricciones
    def test_rn03_rn09_rn10_renovacion_y_restricciones(self):
        hoy = timezone.localdate()
        prestamo = Prestamo.objects.create(
            usuario=self.estudiante,
            ejemplar=self.ejemplares[0],
            estado='ACTIVO',
            fecha_prestamo=timezone.now() - timedelta(days=3),
            fecha_vencimiento=hoy + timedelta(days=4),
            num_renovaciones=0,
        )

        # RN-10: El estudiante renueva el préstamo por primera vez
        self.client.force_login(self.estudiante)
        self.client.post(reverse('renovar_prestamo', args=[prestamo.id]))
        prestamo.refresh_from_db()

        self.assertEqual(prestamo.num_renovaciones, 1)
        self.assertEqual(prestamo.fecha_vencimiento, hoy + timedelta(days=7))

        # RN-03: Intenta renovar una segunda vez (el máximo para estudiante es 1)
        motivo = motivo_no_renovable(prestamo, self.politica_estudiante)
        self.assertIn('máximo de renovaciones', motivo)

        # RN-09: Si otro usuario reserva el título, un préstamo con renovaciones disponibles no puede renovarse
        prestamo_prof = Prestamo.objects.create(
            usuario=self.profesor,
            ejemplar=self.ejemplares[1],
            estado='ACTIVO',
            fecha_vencimiento=hoy + timedelta(days=5),
            num_renovaciones=0,
        )
        Reserva.objects.create(
            usuario=self.estudiante,
            libro=self.libros[1],
            estado='PENDIENTE',
        )
        motivo_reserva = motivo_no_renovable(prestamo_prof, self.politica_profesor)
        self.assertIn('reservó este título', motivo_reserva)

    # RN-11: Verifica que un usuario no pueda tener dos préstamos activos del mismo título
    def test_rn11_no_duplicar_prestamo_mismo_titulo(self):
        # Agrega un segundo ejemplar disponible al mismo Libro 1
        segundo_ejemplar = Ejemplar.objects.create(
            libro=self.libros[0],
            codigo_inventario='INV-TEST-01-B',
            estado='DISPONIBLE',
        )

        self.client.force_login(self.estudiante)
        # Primera solicitud del Libro 1: exitosa
        self.client.post(reverse('solicitar_prestamo', args=[self.libros[0].id]))
        self.assertEqual(Prestamo.objects.filter(usuario=self.estudiante, ejemplar__libro=self.libros[0]).count(), 1)

        # Segunda solicitud del mismo Libro 1: debe rechazarse por RN-11
        self.client.post(reverse('solicitar_prestamo', args=[self.libros[0].id]))
        self.assertEqual(Prestamo.objects.filter(usuario=self.estudiante, ejemplar__libro=self.libros[0]).count(), 1)
        segundo_ejemplar.refresh_from_db()
        self.assertEqual(segundo_ejemplar.estado, 'DISPONIBLE')

    # RN-12: Verifica que las reservas se atiendan en orden FIFO al devolverse un ejemplar
    def test_rn12_cola_fifo_reservas_al_devolver(self):
        ejemplar = self.ejemplares[0]
        ejemplar.estado = 'PRESTADO'
        ejemplar.save()

        ahora = timezone.now()
        # Estudiante 1 reserva primero; Estudiante 2 reserva después
        reserva_1 = Reserva.objects.create(
            usuario=self.estudiante,
            libro=self.libros[0],
            estado='PENDIENTE',
            fecha_reserva=ahora - timedelta(Hours=2) if hasattr(timedelta, 'Hours') else ahora - timedelta(hours=2),
        )
        reserva_2 = Reserva.objects.create(
            usuario=self.estudiante_dos,
            libro=self.libros[0],
            estado='PENDIENTE',
            fecha_reserva=ahora - timedelta(hours=1),
        )

        # Se libera el ejemplar devuelto: debe asignarse a reserva_1 (la más antigua)
        asignada = liberar_o_asignar_ejemplar(ejemplar, ahora)
        reserva_1.refresh_from_db()
        reserva_2.refresh_from_db()
        ejemplar.refresh_from_db()

        self.assertEqual(asignada.id, reserva_1.id)
        self.assertEqual(reserva_1.estado, 'DISPONIBLE')
        self.assertEqual(reserva_1.ejemplar_asignado, ejemplar)
        self.assertEqual(reserva_2.estado, 'PENDIENTE')
        self.assertEqual(ejemplar.estado, 'RESERVADO')
        self.assertTrue(
            Notificacion.objects.filter(usuario=self.estudiante, tipo='RESERVA_DISPONIBLE').exists()
        )

    # RN-15: Verifica que un ejemplar EN_REPARACION, PERDIDO o BAJA no pueda prestarse
    def test_rn15_ejemplar_no_disponible_no_se_presta(self):
        self.ejemplares[0].estado = 'EN_REPARACION'
        self.ejemplares[0].save()

        self.client.force_login(self.bibliotecario)
        self.client.post(reverse('registrar_prestamo_mostrador'), {
            'username': self.estudiante.username,
            'codigo_inventario': self.ejemplares[0].codigo_inventario,
        })

        # Verifica que no se haya creado el préstamo
        self.assertFalse(
            Prestamo.objects.filter(ejemplar=self.ejemplares[0]).exists()
        )
