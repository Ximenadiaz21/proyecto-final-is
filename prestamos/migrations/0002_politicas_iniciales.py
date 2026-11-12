from django.db import migrations
from django.utils import timezone


def crear_politicas(apps, schema_editor):
    Politica = apps.get_model('prestamos', 'PoliticaPrestamo')
    iniciales = [
        ('ESTUDIANTE', 7, 3, 1),
        ('PROFESOR', 30, 10, 2),
    ]
    for tipo, dias, libros, renov in iniciales:
        Politica.objects.get_or_create(
            tipo_usuario=tipo,
            defaults=dict(
                dias_prestamo=dias,
                max_libros=libros,
                max_renovaciones=renov,
                multa_por_dia='10.00',
                multa_maxima='300.00',
                horas_para_recoger=48,
                actualizado_en=timezone.now(),
            ),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('prestamos', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_politicas, migrations.RunPython.noop),
    ]
