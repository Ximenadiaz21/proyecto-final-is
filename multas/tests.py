from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Categoria, Editorial, Ejemplar, Libro
from cuentas.models import Usuario
from prestamos.models import PoliticaPrestamo, Prestamo
from .models import Multa, Pago


# Pruebas unitarias de multas, pagos, condonaciones y daño/pérdida (RN-13, RN-14, CU-27, CU-28, CU-29)
class MultasYPagosTests(TestCase):

    # Configura datos iniciales de prueba
    def setUp(self):
        PoliticaPrestamo.objects.update_or_create(
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

        self.estudiante = Usuario.objects.create_user(
            username='lector_multa',
            password='password123',
            email='lector@test.mx',
            tipo_usuario='ESTUDIANTE',
        )
        self.bibliotecario = Usuario.objects.create_user(
            username='biblio_multa',
            password='password123',
            email='biblio_multa@test.mx',
            tipo_usuario='BIBLIOTECARIO',
        )

        editorial = Editorial.objects.create(nombre='Fondo Cultural', pais='México')
        categoria = Categoria.objects.create(nombre='Ciencias')

        self.libro = Libro.objects.create(
            isbn='9781234567890',
            titulo='Física Universitaria',
            editorial=editorial,
            categoria=categoria,
            costo_reposicion=Decimal('420.00'),
            activo=True,
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            codigo_inventario='INV-MULTA-01',
            estado='PRESTADO',
        )
        self.prestamo = Prestamo.objects.create(
            usuario=self.estudiante,
            ejemplar=self.ejemplar,
            estado='ACTIVO',
            fecha_prestamo=timezone.now(),
            fecha_vencimiento=timezone.localdate(),
        )

    # RN-13 y CU-27: Verifica que al reportar pérdida o daño se genere multa por el costo de reposición
    def test_rn13_multa_por_perdida_usa_costo_reposicion(self):
        self.client.force_login(self.bibliotecario)
        self.client.post(reverse('registrar_incidente_ejemplar', args=[self.prestamo.id]), {
            'motivo': 'PERDIDA',
            'observaciones': 'El alumno extravió el ejemplar.',
        })

        self.prestamo.refresh_from_db()
        self.ejemplar.refresh_from_db()
        multa = Multa.objects.get(prestamo=self.prestamo, motivo='PERDIDA')

        self.assertEqual(self.prestamo.estado, 'PERDIDO')
        self.assertEqual(self.ejemplar.estado, 'PERDIDO')
        self.assertEqual(multa.monto, Decimal('420.00'))
        self.assertEqual(multa.estado, 'PENDIENTE')

    # CU-28: Verifica el registro de pagos parciales y liquidación total de una multa
    def test_cu28_pago_parcial_y_total_de_multa(self):
        multa = Multa.objects.create(
            prestamo=self.prestamo,
            usuario=self.estudiante,
            motivo='RETRASO',
            dias_retraso=5,
            monto=Decimal('50.00'),
            estado='PENDIENTE',
        )

        self.client.force_login(self.bibliotecario)

        # 1. Registra un pago parcial de $20.00 MXN
        self.client.post(reverse('registrar_pago', args=[multa.id]), {
            'monto': '20.00',
            'metodo': 'EFECTIVO',
        })
        multa.refresh_from_db()
        self.assertEqual(multa.estado, 'PENDIENTE')
        self.assertEqual(Pago.objects.filter(multa=multa).count(), 1)

        # 2. Liquida los $30.00 MXN restantes -> la multa pasa a PAGADA
        self.client.post(reverse('registrar_pago', args=[multa.id]), {
            'monto': '30.00',
            'metodo': 'TARJETA',
        })
        multa.refresh_from_db()
        self.assertEqual(multa.estado, 'PAGADA')
        self.assertEqual(Pago.objects.filter(multa=multa).count(), 2)

    # RN-14 y CU-29: Verifica que solo el bibliotecario pueda condonar una multa y que requiera justificación
    def test_rn14_condonar_multa_exige_justificacion(self):
        multa = Multa.objects.create(
            prestamo=self.prestamo,
            usuario=self.estudiante,
            motivo='RETRASO',
            dias_retraso=3,
            monto=Decimal('30.00'),
            estado='PENDIENTE',
        )

        self.client.force_login(self.bibliotecario)

        # Intenta condonar sin justificación -> permanece PENDIENTE
        self.client.post(reverse('condonar_multa', args=[multa.id]), {
            'justificacion': '   ',
        })
        multa.refresh_from_db()
        self.assertEqual(multa.estado, 'PENDIENTE')

        # Condona con justificación válida -> pasa a CONDONADA y registra al bibliotecario
        self.client.post(reverse('condonar_multa', args=[multa.id]), {
            'justificacion': 'Comprobante médico presentado en dirección.',
        })
        multa.refresh_from_db()
        self.assertEqual(multa.estado, 'CONDONADA')
        self.assertEqual(multa.condonada_por, self.bibliotecario)
        self.assertEqual(multa.justificacion_condonacion, 'Comprobante médico presentado en dirección.')
