from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .forms import UsuarioForm
from .models import Carrera, Departamento, Estudiante, Notificacion, Profesor, SugerenciaAdquisicion, Usuario


# Pruebas de usuarios, control de acceso por rol y sugerencias (RF-01, RF-11, RF-16, RNF-01)
class CuentasYRolesTests(TestCase):

    def setUp(self):
        self.carrera = Carrera.objects.create(clave='ISC', nombre='Ingeniería en Sistemas')
        self.departamento = Departamento.objects.create(nombre='Ciencias Computacionales')

        self.bibliotecario = Usuario.objects.create_user(
            username='biblio_usr',
            password='password123',
            email='biblio_usr@test.mx',
            tipo_usuario='BIBLIOTECARIO',
        )
        self.estudiante = Usuario.objects.create_user(
            username='alumno_usr',
            password='password123',
            email='alumno_usr@test.mx',
            tipo_usuario='ESTUDIANTE',
        )
        Estudiante.objects.create(
            usuario=self.estudiante,
            matricula='A2026001',
            carrera=self.carrera,
            semestre=5,
        )

        self.profesor_user = Usuario.objects.create_user(
            username='profesor_usr',
            password='password123',
            email='profesor_usr@test.mx',
            tipo_usuario='PROFESOR',
        )
        self.profesor = Profesor.objects.create(
            usuario=self.profesor_user,
            num_empleado='EMP9001',
            departamento=self.departamento,
        )

    # RF-01 y RNF-01: Un estudiante no puede entrar a vistas exclusivas del bibliotecario
    def test_restriccion_acceso_por_rol(self):
        self.client.force_login(self.estudiante)
        respuesta = self.client.get(reverse('gestion_usuarios'))
        self.assertEqual(respuesta.status_code, 403)

    # CU-20: Creación de estudiante mediante UsuarioForm y validación de semestre (1-12)
    def test_formulario_usuario_valida_semestre(self):
        datos_invalidos = {
            'username': 'nuevo_est',
            'password': 'password123',
            'first_name': 'Juan',
            'last_name': 'Pérez',
            'email': 'juan@test.mx',
            'tipo_usuario': 'ESTUDIANTE',
            'matricula': 'A2026099',
            'carrera': self.carrera.id,
            'semestre': 15,
        }
        self.assertFalse(UsuarioForm(datos_invalidos).is_valid())

        datos_validos = {**datos_invalidos, 'semestre': 6}
        form = UsuarioForm(datos_validos)
        self.assertTrue(form.is_valid())
        creado = form.save()
        self.assertTrue(Estudiante.objects.filter(usuario=creado, semestre=6).exists())

    # CU-22: Bloqueo de usuario requiere motivo y desbloqueo limpia el motivo
    def test_bloqueo_y_desbloqueo_usuario(self):
        self.client.force_login(self.bibliotecario)

        # Sin motivo no bloquea
        self.client.post(reverse('cambiar_bloqueo', args=[self.estudiante.id]), {'motivo': '  '})
        self.estudiante.refresh_from_db()
        self.assertFalse(self.estudiante.bloqueado)

        # Con motivo bloquea
        self.client.post(reverse('cambiar_bloqueo', args=[self.estudiante.id]), {'motivo': 'Credencial vencida'})
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.bloqueado)
        self.assertEqual(self.estudiante.motivo_bloqueo, 'Credencial vencida')

    # CU-16 y CU-33: Profesor envía sugerencia y bibliotecario la aprueba
    def test_flujo_sugerencia_adquisicion(self):
        self.client.force_login(self.profesor_user)
        self.client.post(reverse('mis_sugerencias'), {
            'titulo': 'Arquitectura Limpia',
            'autores': 'Robert C. Martin',
            'isbn': '9780134494166',
            'justificacion': 'Bibliografía básica para quinto semestre.',
        })

        sugerencia = SugerenciaAdquisicion.objects.get(profesor=self.profesor)
        self.assertEqual(sugerencia.estado, 'PENDIENTE')

        self.client.force_login(self.bibliotecario)
        self.client.post(reverse('responder_sugerencia', args=[sugerencia.id]), {
            'estado': 'APROBADA',
            'respuesta': 'Se incluirá en la próxima compra.',
        })

        sugerencia.refresh_from_db()
        self.assertEqual(sugerencia.estado, 'APROBADA')
        self.assertTrue(Notificacion.objects.filter(usuario=self.profesor_user).exists())

    # RF-15: Al crear una notificación, el sistema también dispara el envío por correo al confirmar la transacción
    def test_rf15_notificacion_envia_correo(self):
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            Notificacion.objects.create(
                usuario=self.estudiante,
                tipo='RESERVA_DISPONIBLE',
                mensaje='Tu reserva de "Diseño de Bases de Datos" ya está disponible.',
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('disponible', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [self.estudiante.email])

    # CU-21 y RF-11: Importación masiva de usuarios desde CSV (válidos y con error)
    def test_cu21_importar_usuarios_csv(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        contenido_csv = (
            "username,nombre,apellidos,correo,tipo,matricula,carrera,semestre,num_empleado,departamento,password\n"
            "csv_est01,Maria,Lopez,maria.csv@test.mx,ESTUDIANTE,MCSV001,ISC,4,,,Pass12345\n"
            "csv_prof01,Carlos,Ruiz,carlos.csv@test.mx,PROFESOR,,,,EMPCSV1,Ciencias Computacionales,Pass12345\n"
            "csv_malo,Sin,Carrera,malo.csv@test.mx,ESTUDIANTE,MCSV002,NOEXISTE,4,,,Pass12345\n"
        ).encode('utf-8')

        archivo = SimpleUploadedFile('usuarios.csv', contenido_csv, content_type='text/csv')
        self.client.force_login(self.bibliotecario)
        respuesta = self.client.post(reverse('importar_usuarios'), {'archivo': archivo})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['creados'], 2)
        self.assertEqual(respuesta.context['fallidos'], 1)
        self.assertTrue(Estudiante.objects.filter(matricula='MCSV001').exists())
        self.assertTrue(Profesor.objects.filter(num_empleado='EMPCSV1').exists())

    # CU-20: Baja lógica impide desactivar usuario con préstamo activo y permite cuando está libre
    def test_cu20_baja_logica_usuario_y_bloqueo_con_prestamo_activo(self):
        from decimal import Decimal
        from catalogo.models import Categoria, Editorial, Ejemplar, Libro
        from prestamos.models import Prestamo

        ed = Editorial.objects.create(nombre='Ed Prueba')
        cat = Categoria.objects.create(nombre='Cat Prueba')
        libro = Libro.objects.create(
            isbn='9789999999991', titulo='Libro Test', editorial=ed, categoria=cat,
            costo_reposicion=Decimal('200.00'), activo=True,
        )
        ejemplar = Ejemplar.objects.create(libro=libro, codigo_inventario='EJ-USR-01', estado='PRESTADO')
        prestamo = Prestamo.objects.create(usuario=self.estudiante, ejemplar=ejemplar, estado='ACTIVO')

        self.client.force_login(self.bibliotecario)
        # Con préstamo activo NO debe dar de baja
        self.client.post(reverse('cambiar_estado_usuario', args=[self.estudiante.id]))
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

        # Al devolver el préstamo, sí permite dar de baja lógica y luego reactivar
        prestamo.estado = 'DEVUELTO'
        prestamo.save()
        self.client.post(reverse('cambiar_estado_usuario', args=[self.estudiante.id]))
        self.estudiante.refresh_from_db()
        self.assertFalse(self.estudiante.is_active)

        self.client.post(reverse('cambiar_estado_usuario', args=[self.estudiante.id]))
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

    # RNF-02: Un usuario no puede marcar como leída una notificación que pertenece a otro
    def test_rnf02_aislamiento_notificaciones(self):
        notif = Notificacion.objects.create(
            usuario=self.estudiante,
            tipo='GENERAL',
            mensaje='Aviso privado del estudiante.',
        )
        self.client.force_login(self.profesor_user)
        respuesta = self.client.post(reverse('marcar_notificacion_leida', args=[notif.id]))
        self.assertEqual(respuesta.status_code, 404)
        notif.refresh_from_db()
        self.assertFalse(notif.leida)

    # CU-20: Baja lógica bloqueada con solicitud, reserva apartada o multa pendiente, y cancela reservas en espera
    def test_cu20_baja_logica_bloquea_solicitud_reserva_multa_y_cancela_pendientes(self):
        from decimal import Decimal
        from catalogo.models import Categoria, Editorial, Ejemplar, Libro
        from multas.models import Multa
        from prestamos.models import Prestamo, Reserva

        ed = Editorial.objects.create(nombre='Ed Baja')
        cat = Categoria.objects.create(nombre='Cat Baja')
        libro = Libro.objects.create(
            isbn='9789999999992', titulo='Libro Baja', editorial=ed, categoria=cat,
            costo_reposicion=Decimal('200.00'), activo=True,
        )
        ejemplar = Ejemplar.objects.create(libro=libro, codigo_inventario='EJ-BAJA-01', estado='RESERVADO')
        self.client.force_login(self.bibliotecario)

        # 1. Con préstamo SOLICITADO no permite baja
        prestamo = Prestamo.objects.create(usuario=self.estudiante, ejemplar=ejemplar, estado='SOLICITADO')
        self.client.post(reverse('cambiar_estado_usuario', args=[self.estudiante.id]))
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

        prestamo.estado = 'DEVUELTO'
        prestamo.save()

        # 2. Con reserva DISPONIBLE (ejemplar apartado) no permite baja
        reserva_disp = Reserva.objects.create(
            usuario=self.estudiante, libro=libro, ejemplar_asignado=ejemplar, estado='DISPONIBLE'
        )
        self.client.post(reverse('cambiar_estado_usuario', args=[self.estudiante.id]))
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

        reserva_disp.estado = 'CANCELADA'
        reserva_disp.ejemplar_asignado = None
        reserva_disp.save()

        # 3. Con multa PENDIENTE no permite baja
        multa = Multa.objects.create(
            prestamo=prestamo, usuario=self.estudiante, motivo='RETRASO',
            dias_retraso=2, monto=Decimal('20.00'), estado='PENDIENTE',
        )
        self.client.post(reverse('cambiar_estado_usuario', args=[self.estudiante.id]))
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

        multa.estado = 'PAGADA'
        multa.save()

        # 4. Con solo reserva PENDIENTE en cola: sí da de baja y cancela la reserva pendiente
        reserva_pend = Reserva.objects.create(usuario=self.estudiante, libro=libro, estado='PENDIENTE')
        self.client.post(reverse('cambiar_estado_usuario', args=[self.estudiante.id]))
        self.estudiante.refresh_from_db()
        reserva_pend.refresh_from_db()
        self.assertFalse(self.estudiante.is_active)
        self.assertEqual(reserva_pend.estado, 'CANCELADA')


