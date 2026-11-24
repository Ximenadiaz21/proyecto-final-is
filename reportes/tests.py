from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalogo.models import Categoria, Editorial, Ejemplar, Libro
from cuentas.models import Usuario
from multas.models import Multa, Pago
from prestamos.models import PoliticaPrestamo, Prestamo


# Pruebas de reportes operativos, exportación CSV y carga demo (CU-32, RF-14, RNF-08)
class ReportesYExportacionTests(TestCase):

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
            },
        )
        self.bibliotecario = Usuario.objects.create_user(
            username='biblio_rep',
            password='password123',
            email='biblio_rep@test.mx',
            tipo_usuario='BIBLIOTECARIO',
        )
        self.estudiante = Usuario.objects.create_user(
            username='est_rep',
            password='password123',
            email='est_rep@test.mx',
            tipo_usuario='ESTUDIANTE',
        )

        editorial = Editorial.objects.create(nombre='Ed Reporte')
        categoria = Categoria.objects.create(nombre='Cat Reporte')
        self.libro = Libro.objects.create(
            isbn='9786071500111',
            titulo='Libro de Reporte',
            editorial=editorial,
            categoria=categoria,
            costo_reposicion=Decimal('250.00'),
            activo=True,
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            codigo_inventario='EJ-REP-CSV-1',
            estado='PRESTADO',
        )
        self.prestamo = Prestamo.objects.create(
            usuario=self.estudiante,
            ejemplar=self.ejemplar,
            estado='VENCIDO',
        )
        self.multa = Multa.objects.create(
            prestamo=self.prestamo,
            usuario=self.estudiante,
            motivo='RETRASO',
            dias_retraso=4,
            monto=Decimal('40.00'),
            estado='PENDIENTE',
        )
        Pago.objects.create(
            multa=self.multa,
            monto=Decimal('15.00'),
            metodo='EFECTIVO',
            folio_recibo='REC-REP-01',
            registrado_por=self.bibliotecario,
        )

    # RF-01 / RNF-01: Solo el bibliotecario puede ver reportes o exportarlos a CSV
    def test_acceso_reportes_y_csv_solo_bibliotecario(self):
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get(reverse('reportes')).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('exportar_reporte_csv', args=['prestamos'])).status_code,
            403,
        )

    # CU-32: Exportación CSV de los 4 reportes devuelve UTF-8 con datos y 404 para tipo inválido
    def test_cu32_exportacion_csv_cuatro_reportes(self):
        self.client.force_login(self.bibliotecario)

        for tipo, esperado in [
            ('prestamos', 'EJ-REP-CSV-1'),
            ('libros', 'Libro de Reporte'),
            ('vencidos', 'est_rep'),
            ('multas', '40.00'),
        ]:
            resp = self.client.get(reverse('exportar_reporte_csv', args=[tipo]))
            self.assertEqual(resp.status_code, 200)
            self.assertIn('text/csv', resp['Content-Type'])
            self.assertIn(esperado, resp.content.decode('utf-8-sig'))

        self.assertEqual(
            self.client.get(reverse('exportar_reporte_csv', args=['invalido'])).status_code,
            404,
        )

    # CU-32: El total cobrado de multas respeta el rango de fechas seleccionado
    def test_cu32_reporte_multas_cobradas_filtra_por_periodo(self):
        from datetime import timedelta
        from django.utils import timezone

        hace_60_dias = timezone.now() - timedelta(days=60)
        Pago.objects.create(
            multa=self.multa,
            monto=Decimal('25.00'),
            metodo='TARJETA',
            folio_recibo='REC-REP-ANTIGUO',
            fecha_pago=hace_60_dias,
            registrado_por=self.bibliotecario,
        )

        self.client.force_login(self.bibliotecario)
        # Periodo por defecto (últimos 30 días): solo cuenta el pago de hoy ($15.00)
        resp_reciente = self.client.get(reverse('reportes'))
        self.assertEqual(resp_reciente.context['total_cobrado'], Decimal('15.00'))

        # Ampliando fecha_inicio a 90 días atrás: incluye ambos pagos ($40.00)
        hoy = timezone.localdate()
        resp_amplio = self.client.get(reverse('reportes'), {
            'fecha_inicio': (hoy - timedelta(days=90)).isoformat(),
            'fecha_fin': hoy.isoformat(),
        })
        self.assertEqual(resp_amplio.context['total_cobrado'], Decimal('40.00'))


# Pruebas del comando de carga operativa de demostración en base limpia (RNF-08)
class DemoOperacionCommandTests(TestCase):

    # RNF-08: demo_operacion carga usuarios, libros y operación completa y es idempotente
    def test_rnf08_comando_demo_operacion_idempotente(self):
        call_command('demo_operacion')

        conteo_prestamos = Prestamo.objects.count()
        self.assertGreaterEqual(conteo_prestamos, 10)
        self.assertGreaterEqual(Multa.objects.count(), 3)

        # Ejecutarlo una segunda vez no debe duplicar préstamos ni fallar
        call_command('demo_operacion')
        self.assertEqual(Prestamo.objects.count(), conteo_prestamos)

        # Verifica que la vista de reportes cargue con cifras reales para el bibliotecario
        bibliotecario = Usuario.objects.filter(tipo_usuario='BIBLIOTECARIO').first()
        self.client.force_login(bibliotecario)
        resp = self.client.get(reverse('reportes'))
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(resp.context['total_prestamos_periodo'], 0)
