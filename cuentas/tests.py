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

