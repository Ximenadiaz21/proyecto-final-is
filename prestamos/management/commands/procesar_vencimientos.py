from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from prestamos import servicios


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

        ahora = timezone.now()
        hoy = timezone.localdate()

        if simular:
            self.stdout.write(self.style.WARNING('Modo simulación: no se guardará ningún cambio.'))

        vencidos = servicios.marcar_prestamos_vencidos(hoy=hoy, ahora=ahora, simular=simular)
        expiradas = servicios.expirar_solicitudes(ahora=ahora, simular=simular)
        reservas = servicios.expirar_reservas(ahora=ahora, simular=simular)
        avisos = servicios.enviar_recordatorios(
            dias_aviso=dias_aviso, hoy=hoy, ahora=ahora, simular=simular
        )

        verbo = 'Se marcarían' if simular else 'Se marcaron'
        self.stdout.write(self.style.SUCCESS(f"{verbo} {vencidos} préstamo(s) como VENCIDO."))
        self.stdout.write(self.style.SUCCESS(f"{verbo} {expiradas} solicitud(es) como EXPIRADO."))
        self.stdout.write(self.style.SUCCESS(f"{verbo} {reservas} reserva(s) como EXPIRADA."))
        verbo_aviso = 'Se enviarían' if simular else 'Se enviaron'
        self.stdout.write(self.style.SUCCESS(f"{verbo_aviso} {avisos} recordatorio(s) de vencimiento."))
