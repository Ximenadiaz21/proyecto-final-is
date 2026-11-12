from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalogo.models import Ejemplar
from cuentas.models import Notificacion
from prestamos.models import Prestamo, Reserva


class Command(BaseCommand):
    help = (
        "Marca los préstamos vencidos (CU-34), expira solicitudes y reservas no "
        "atendidas (CU-35) y avisa de los vencimientos próximos (CU-36)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra lo que haría sin guardar ningún cambio.',
        )
        parser.add_argument(
            '--dias-aviso', type=int, default=2,
            help='Días de anticipación para el recordatorio de vencimiento (por defecto 2).',
        )

    def handle(self, *args, **opciones):
        simular = opciones['dry_run']
        dias_aviso = opciones['dias_aviso']

        if dias_aviso < 0:
            raise CommandError('--dias-aviso no puede ser negativo.')

        self.simular = simular
        self.ahora = timezone.now()
        self.hoy = timezone.localdate()

        if simular:
            self.stdout.write(self.style.WARNING('Modo simulación: no se guardará ningún cambio.'))

        vencidos = self._marcar_vencidos()
        expiradas = self._expirar_solicitudes()
        reservas = self._expirar_reservas()
        avisos = self._recordatorios(dias_aviso)

        verbo = 'Se marcarían' if simular else 'Se marcaron'
        self.stdout.write(self.style.SUCCESS(f"{verbo} {vencidos} préstamo(s) como VENCIDO."))
        self.stdout.write(self.style.SUCCESS(f"{verbo} {expiradas} solicitud(es) como EXPIRADO."))
        self.stdout.write(self.style.SUCCESS(f"{verbo} {reservas} reserva(s) como EXPIRADA."))
        verbo_aviso = 'Se enviarían' if simular else 'Se enviaron'
        self.stdout.write(self.style.SUCCESS(f"{verbo_aviso} {avisos} recordatorio(s) de vencimiento."))

    # Guarda un aviso para el usuario
    def _notificar(self, usuario, tipo, mensaje):
        Notificacion.objects.create(
            usuario=usuario, tipo=tipo, mensaje=mensaje, leida=0, fecha=self.ahora
        )

    # Libera un ejemplar apartado (RESERVADO -> DISPONIBLE)
    def _liberar_ejemplar(self, ejemplar_id):
        if not ejemplar_id:
            return
        ejemplar = Ejemplar.objects.select_for_update().get(pk=ejemplar_id)
        if ejemplar.estado == 'RESERVADO':
            ejemplar.estado = 'DISPONIBLE'
            ejemplar.save(update_fields=['estado'])

    # CU-34: ACTIVO con la fecha de vencimiento pasada -> VENCIDO
    def _marcar_vencidos(self):
        ids = list(Prestamo.objects.filter(
            estado='ACTIVO', fecha_vencimiento__lt=self.hoy
        ).values_list('id', flat=True))

        if self.simular:
            return len(ids)

        total = 0
        for prestamo_id in ids:
            with transaction.atomic():
                prestamo = Prestamo.objects.select_for_update().get(pk=prestamo_id)
                if prestamo.estado != 'ACTIVO':
                    continue

                prestamo.estado = 'VENCIDO'
                prestamo.save(update_fields=['estado'])

                self._notificar(
                    prestamo.usuario, 'VENCIDO',
                    f"Tu préstamo de «{prestamo.ejemplar.libro.titulo}» venció el "
                    f"{prestamo.fecha_vencimiento:%d/%m/%Y}. Devuélvelo lo antes posible para evitar más multa."
                )
                total += 1

        return total

    # CU-35: SOLICITADO que no se recogió a tiempo -> EXPIRADO y libera el ejemplar
    def _expirar_solicitudes(self):
        ids = list(Prestamo.objects.filter(
            estado='SOLICITADO', fecha_limite_recoger__lt=self.ahora
        ).values_list('id', flat=True))

        if self.simular:
            return len(ids)

        total = 0
        for prestamo_id in ids:
            with transaction.atomic():
                prestamo = Prestamo.objects.select_for_update().get(pk=prestamo_id)
                if prestamo.estado != 'SOLICITADO':
                    continue

                prestamo.estado = 'EXPIRADO'
                prestamo.save(update_fields=['estado'])
                self._liberar_ejemplar(prestamo.ejemplar_id)

                self._notificar(
                    prestamo.usuario, 'GENERAL',
                    f"Tu solicitud de «{prestamo.ejemplar.libro.titulo}» expiró porque no se "
                    f"recogió a tiempo. Puedes solicitarlo de nuevo si sigue disponible."
                )
                total += 1

        return total

    # CU-35: reserva con ejemplar apartado que no se recogió a tiempo -> EXPIRADA
    def _expirar_reservas(self):
        ids = list(Reserva.objects.filter(
            estado='DISPONIBLE', fecha_expiracion__lt=self.ahora
        ).values_list('id', flat=True))

        if self.simular:
            return len(ids)

        total = 0
        for reserva_id in ids:
            with transaction.atomic():
                reserva = Reserva.objects.select_for_update().get(pk=reserva_id)
                if reserva.estado != 'DISPONIBLE':
                    continue

                reserva.estado = 'EXPIRADA'
                reserva.save(update_fields=['estado'])
                self._liberar_ejemplar(reserva.ejemplar_asignado_id)

                self._notificar(
                    reserva.usuario, 'GENERAL',
                    f"Tu reserva de «{reserva.libro.titulo}» expiró porque no se recogió a tiempo."
                )
                total += 1

        return total

    # CU-36: avisa de los préstamos que vencen en los próximos días (una sola vez por préstamo)
    def _recordatorios(self, dias_aviso):
        limite = self.hoy + timedelta(days=dias_aviso)
        prestamos = Prestamo.objects.filter(
            estado='ACTIVO', fecha_vencimiento__gte=self.hoy, fecha_vencimiento__lte=limite
        ).select_related('usuario', 'ejemplar__libro')

        total = 0
        for prestamo in prestamos:
            mensaje = (
                f"Tu préstamo de «{prestamo.ejemplar.libro.titulo}» vence el "
                f"{prestamo.fecha_vencimiento:%d/%m/%Y}. Devuélvelo a tiempo para evitar multas."
            )

            ya_avisado = Notificacion.objects.filter(
                usuario=prestamo.usuario, tipo='VENCE_PRONTO', mensaje=mensaje
            ).exists()
            if ya_avisado:
                continue

            if not self.simular:
                self._notificar(prestamo.usuario, 'VENCE_PRONTO', mensaje)
            total += 1

        return total
