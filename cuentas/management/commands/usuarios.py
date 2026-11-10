
from django.core.management.base import BaseCommand
from django.db import transaction
from cuentas.models import Usuario, Estudiante, Profesor, Carrera, Departamento


class Command(BaseCommand):
    help = 'Crea usuarios de prueba para la biblioteca'

    @transaction.atomic
    def handle(self, *args, **options):

        # Contraseña utilizada únicamente para las cuentas ficticias
        password = 'passbiblio'

        # Crea las carreras necesarias sin duplicar las existentes
        carreras = [
            ('SIS', 'Ingeniería en Sistemas'),
            ('IND', 'Ingeniería Industrial'),
            ('MEC', 'Ingeniería Mecatrónica'),
            ('DER', 'Derecho'),
            ('ADM', 'Administración de Empresas'),
        ]

        for clave, nombre in carreras:
            Carrera.objects.get_or_create(
                clave=clave,
                defaults={'nombre': nombre}
            )

        # Crea los departamentos académicos si todavía no existen
        departamentos = [
            'Ingeniería',
            'Matemáticas',
            'Ciencias Básicas',
            'Humanidades',
            'Administración',
        ]

        for nombre in departamentos:
            Departamento.objects.get_or_create(nombre=nombre)

        carreras = list(Carrera.objects.order_by('id'))
        departamentos = list(Departamento.objects.order_by('id'))

        # Crea 20 estudiantes con matrícula, carrera y semestre
        for i in range(1, 21):
            username = f'alumno{i:02d}'

            usuario, creado = Usuario.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': f'Estudiante {i}',
                    'last_name': 'Prueba',
                    'email': f'alumno{i:02d}@example.com',
                    'tipo_usuario': 'ESTUDIANTE',
                    'is_active': True,
                }
            )

            if creado:
                usuario.set_password(password)
                usuario.save()

            # Relaciona al estudiante con su cuenta de usuario
            if usuario.tipo_usuario == 'ESTUDIANTE':
                Estudiante.objects.get_or_create(
                    usuario=usuario,
                    defaults={
                        'matricula': f'DEMO{i:05d}',
                        'carrera': carreras[(i - 1) % len(carreras)],
                        'semestre': ((i - 1) % 12) + 1,
                    }
                )

        # Crea 5 profesores con número de empleado y departamento
        for i in range(1, 6):
            username = f'profesor{i:02d}'

            usuario, creado = Usuario.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': f'Profesor {i}',
                    'last_name': 'Prueba',
                    'email': f'profesor{i:02d}@example.com',
                    'tipo_usuario': 'PROFESOR',
                    'is_active': True,
                }
            )

            if creado:
                usuario.set_password(password)
                usuario.save()

            # Guarda el perfil académico del profesor
            if usuario.tipo_usuario == 'PROFESOR':
                Profesor.objects.get_or_create(
                    usuario=usuario,
                    defaults={
                        'num_empleado': f'PROF{i:04d}',
                        'departamento': departamentos[(i - 1) % len(departamentos)],
                    }
                )

        # Crea un bibliotecario adicional sin modificar el existente
        usuario, creado = Usuario.objects.get_or_create(
            username='bibliotecario_demo',
            defaults={
                'first_name': 'Bibliotecario',
                'last_name': 'Prueba',
                'email': 'bibliotecario.demo@example.com',
                'tipo_usuario': 'BIBLIOTECARIO',
                'is_active': True,
                'is_staff': False,
            }
        )

        if creado:
            usuario.set_password(password)
            usuario.save()

        # Muestra los resultados de la carga
        self.stdout.write(self.style.SUCCESS(
            'Carga de usuarios de prueba completada'
        ))
        self.stdout.write(
            f'Estudiantes: {Estudiante.objects.count()}'
        )
        self.stdout.write(
            f'Profesores: {Profesor.objects.count()}'
        )
        self.stdout.write(
            f'Bibliotecarios: {Usuario.objects.filter(tipo_usuario="BIBLIOTECARIO").count()}'
        )
