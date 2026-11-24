from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from cuentas.models import Notificacion, Profesor, SugerenciaAdquisicion, Usuario
from multas.models import Multa, Pago
from prestamos.models import Prestamo, Reserva


class Command(BaseCommand):
    help = (
        'Carga datos operativos de demostración (préstamos, vencidos, reservas, '
        'multas, pagos, sugerencias y notificaciones) para pruebas y reportes.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # Si aún no existen usuarios o libros de prueba, los carga automáticamente en modo offline
        if not Usuario.objects.filter(tipo_usuario='ESTUDIANTE').exists():
            call_command('usuarios')
        if Libro.objects.count() < 10:
            call_command('libros', offline=True)

        # Idempotencia: si ya hay registros operativos, no duplica datos
        if Prestamo.objects.exists():
            self.stdout.write(self.style.WARNING(
                'Ya existen préstamos registrados. No se duplicaron datos operativos.'
            ))
            return

        ahora = timezone.now()
        hoy = timezone.localdate()

        bibliotecario = Usuario.objects.filter(tipo_usuario='BIBLIOTECARIO').order_by('id').first()
        estudiantes = list(
            Usuario.objects.filter(tipo_usuario='ESTUDIANTE', is_active=True).order_by('username')[:12]
        )
        profesores_u = list(
            Usuario.objects.filter(tipo_usuario='PROFESOR', is_active=True).order_by('username')[:5]
        )
        libros = list(Libro.objects.filter(activo=True).order_by('id')[:12])

        if not bibliotecario or len(estudiantes) < 6 or len(profesores_u) < 2 or len(libros) < 8:
            self.stdout.write(self.style.ERROR(
                'No hay suficientes usuarios o libros base. Ejecuta primero `usuarios` y `libros`.'
            ))
            return

        def ejemplares_de(libro):
            return list(Ejemplar.objects.filter(libro=libro).order_by('id'))

        # 1. Préstamos DEVUELTOS (historial para Reporte 1 y Reporte 2)
        for idx in range(5):
            ej = ejemplares_de(libros[idx])[0]
            lector = estudiantes[idx] if idx % 2 == 0 else profesores_u[idx % len(profesores_u)]
            dias_plazo = 7 if lector.tipo_usuario == 'ESTUDIANTE' else 30
            Prestamo.objects.create(
                usuario=lector,
                ejemplar=ej,
                estado=Prestamo.Estado.DEVUELTO,
                fecha_solicitud=ahora - timedelta(days=18 - idx),
                fecha_prestamo=ahora - timedelta(days=18 - idx),
                fecha_vencimiento=hoy - timedelta(days=18 - idx) + timedelta(days=dias_plazo),
                fecha_devolucion=ahora - timedelta(days=12 - idx),
                entregado_por=bibliotecario,
                recibido_por=bibliotecario,
            )

        # Segundo historial en libros[0] para destacarlo como más solicitado
        ej0_b = ejemplares_de(libros[0])[-1]
        Prestamo.objects.create(
            usuario=estudiantes[1],
            ejemplar=ej0_b,
            estado=Prestamo.Estado.DEVUELTO,
            fecha_solicitud=ahora - timedelta(days=10),
            fecha_prestamo=ahora - timedelta(days=10),
            fecha_vencimiento=hoy - timedelta(days=3),
            fecha_devolucion=ahora - timedelta(days=4),
            entregado_por=bibliotecario,
            recibido_por=bibliotecario,
        )

        # 2. Libro 0 completamente agotado (2 ejemplares PRESTADO) + cola FIFO de 2 reservas (RN-12)
        for pos, ej in enumerate(ejemplares_de(libros[0])[:2]):
            lector = estudiantes[pos]
            Prestamo.objects.create(
                usuario=lector,
                ejemplar=ej,
                estado=Prestamo.Estado.ACTIVO,
                fecha_solicitud=ahora - timedelta(days=2),
                fecha_prestamo=ahora - timedelta(days=2),
                fecha_vencimiento=hoy + timedelta(days=5),
                entregado_por=bibliotecario,
            )
            ej.estado = Ejemplar.Estado.PRESTADO
            ej.save(update_fields=['estado'])

        Reserva.objects.create(
            usuario=estudiantes[2],
            libro=libros[0],
            estado=Reserva.Estado.PENDIENTE,
            fecha_reserva=ahora - timedelta(hours=12),
        )
        Reserva.objects.create(
            usuario=estudiantes[3],
            libro=libros[0],
            estado=Reserva.Estado.PENDIENTE,
            fecha_reserva=ahora - timedelta(hours=4),
        )

        # 3. Préstamo ACTIVO de profesor (30 días, RN-01)
        ej_prof = ejemplares_de(libros[1])[0]
        Prestamo.objects.create(
            usuario=profesores_u[0],
            ejemplar=ej_prof,
            estado=Prestamo.Estado.ACTIVO,
            fecha_solicitud=ahora - timedelta(days=5),
            fecha_prestamo=ahora - timedelta(days=5),
            fecha_vencimiento=hoy + timedelta(days=25),
            entregado_por=bibliotecario,
        )
        ej_prof.estado = Ejemplar.Estado.PRESTADO
        ej_prof.save(update_fields=['estado'])

        # 4. Solicitud pendiente de entrega en mostrador (SOLICITADO)
        ej_sol = ejemplares_de(libros[2])[0]
        Prestamo.objects.create(
            usuario=estudiantes[4],
            ejemplar=ej_sol,
            estado=Prestamo.Estado.SOLICITADO,
            fecha_solicitud=ahora - timedelta(hours=3),
            fecha_limite_recoger=ahora + timedelta(hours=45),
        )
        ej_sol.estado = Ejemplar.Estado.RESERVADO
        ej_sol.save(update_fields=['estado'])

        # 5. Reserva DISPONIBLE con ejemplar apartado listo para entregar (CU-30)
        ej_res = ejemplares_de(libros[3])[0]
        Reserva.objects.create(
            usuario=estudiantes[5],
            libro=libros[3],
            ejemplar_asignado=ej_res,
            estado=Reserva.Estado.DISPONIBLE,
            fecha_reserva=ahora - timedelta(days=2),
            fecha_expiracion=ahora + timedelta(hours=36),
        )
        ej_res.estado = Ejemplar.Estado.RESERVADO
        ej_res.save(update_fields=['estado'])

        # 6. Préstamos VENCIDOS (Reporte 3 y CU-34)
        for idx, (lector, dias_atraso) in enumerate([(estudiantes[6], 5), (profesores_u[1], 3)]):
            ej_v = ejemplares_de(libros[4 + idx])[0]
            Prestamo.objects.create(
                usuario=lector,
                ejemplar=ej_v,
                estado=Prestamo.Estado.VENCIDO,
                fecha_solicitud=ahora - timedelta(days=15),
                fecha_prestamo=ahora - timedelta(days=15),
                fecha_vencimiento=hoy - timedelta(days=dias_atraso),
                entregado_por=bibliotecario,
            )
            ej_v.estado = Ejemplar.Estado.PRESTADO
            ej_v.save(update_fields=['estado'])

        # 7. Multas y Pagos (PENDIENTE, pago parcial, PAGADA, CONDONADA) para Reporte 4
        ej_m1 = ejemplares_de(libros[6])[0]
        p_m1 = Prestamo.objects.create(
            usuario=estudiantes[7],
            ejemplar=ej_m1,
            estado=Prestamo.Estado.DEVUELTO,
            fecha_solicitud=ahora - timedelta(days=20),
            fecha_prestamo=ahora - timedelta(days=20),
            fecha_vencimiento=hoy - timedelta(days=13),
            fecha_devolucion=ahora - timedelta(days=8),
            entregado_por=bibliotecario,
            recibido_por=bibliotecario,
        )
        multa_pend = Multa.objects.create(
            prestamo=p_m1,
            usuario=estudiantes[7],
            motivo=Multa.Motivo.RETRASO,
            dias_retraso=5,
            monto=Decimal('50.00'),
            estado=Multa.Estado.PENDIENTE,
            fecha_generacion=ahora - timedelta(days=8),
        )
        Pago.objects.create(
            multa=multa_pend,
            monto=Decimal('20.00'),
            metodo=Pago.Metodo.EFECTIVO,
            folio_recibo='REC-DEMO-0001',
            fecha_pago=ahora - timedelta(days=6),
            registrado_por=bibliotecario,
        )

        ej_m2 = ejemplares_de(libros[7])[0]
        p_m2 = Prestamo.objects.create(
            usuario=estudiantes[8],
            ejemplar=ej_m2,
            estado=Prestamo.Estado.DEVUELTO,
            fecha_solicitud=ahora - timedelta(days=16),
            fecha_prestamo=ahora - timedelta(days=16),
            fecha_vencimiento=hoy - timedelta(days=9),
            fecha_devolucion=ahora - timedelta(days=6),
            entregado_por=bibliotecario,
            recibido_por=bibliotecario,
        )
        multa_pagada = Multa.objects.create(
            prestamo=p_m2,
            usuario=estudiantes[8],
            motivo=Multa.Motivo.RETRASO,
            dias_retraso=3,
            monto=Decimal('30.00'),
            estado=Multa.Estado.PAGADA,
            fecha_generacion=ahora - timedelta(days=6),
        )
        Pago.objects.create(
            multa=multa_pagada,
            monto=Decimal('30.00'),
            metodo=Pago.Metodo.TARJETA,
            folio_recibo='REC-DEMO-0002',
            fecha_pago=ahora - timedelta(days=5),
            registrado_por=bibliotecario,
        )

        Multa.objects.create(
            prestamo=p_m2,
            usuario=estudiantes[8],
            motivo=Multa.Motivo.RETRASO,
            dias_retraso=2,
            monto=Decimal('20.00'),
            estado=Multa.Estado.CONDONADA,
            fecha_generacion=ahora - timedelta(days=4),
            justificacion_condonacion='Comprobante médico presentado en biblioteca.',
            condonada_por=bibliotecario,
        )

        # 8. Sugerencias de adquisición (CU-16, CU-33)
        perfil_prof = Profesor.objects.filter(usuario=profesores_u[0]).first()
        if perfil_prof:
            SugerenciaAdquisicion.objects.create(
                profesor=perfil_prof,
                titulo='Clean Architecture',
                autores='Robert C. Martin',
                isbn='9780134494166',
                justificacion='Referencia para la materia de Ingeniería de Software.',
                estado=SugerenciaAdquisicion.Estado.PENDIENTE,
                fecha=ahora - timedelta(days=2),
            )
            SugerenciaAdquisicion.objects.create(
                profesor=perfil_prof,
                titulo='Designing Data-Intensive Applications',
                autores='Martin Kleppmann',
                isbn='9781449373320',
                justificacion='Bibliografía recomendada para Bases de Datos Avanzadas.',
                estado=SugerenciaAdquisicion.Estado.APROBADA,
                respuesta='Incluido en el pedido del próximo semestre.',
                fecha=ahora - timedelta(days=7),
            )

        # 9. Notificaciones de ejemplo (directo en BD sin disparar correos masivos)
        Notificacion.objects.bulk_create([
            Notificacion(
                usuario=estudiantes[5],
                tipo=Notificacion.Tipo.RESERVA_DISPONIBLE,
                mensaje=f'Tu reserva de "{libros[3].titulo}" ya está disponible para recoger.',
                leida=False,
                fecha=ahora - timedelta(hours=2),
            ),
            Notificacion(
                usuario=estudiantes[6],
                tipo=Notificacion.Tipo.VENCIDO,
                mensaje=f'Tu préstamo de "{libros[4].titulo}" está vencido. Devuélvelo cuanto antes.',
                leida=False,
                fecha=ahora - timedelta(days=1),
            ),
            Notificacion(
                usuario=estudiantes[7],
                tipo=Notificacion.Tipo.MULTA,
                mensaje='Tienes una multa pendiente con saldo de $30.00 MXN.',
                leida=False,
                fecha=ahora - timedelta(days=6),
            ),
        ])

        self.stdout.write(self.style.SUCCESS(
            f'Datos operativos de demostración cargados: '
            f'{Prestamo.objects.count()} préstamos, '
            f'{Reserva.objects.count()} reservas, '
            f'{Multa.objects.count()} multas, '
            f'{Pago.objects.count()} pagos, '
            f'{SugerenciaAdquisicion.objects.count()} sugerencias.'
        ))
