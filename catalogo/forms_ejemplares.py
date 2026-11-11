import re

from django import forms
from django.db import transaction
from django.utils import timezone

from prestamos.models import Prestamo
from .models import Libro, Ejemplar

ESTADOS = [
    ('DISPONIBLE', 'Disponible'),
    ('RESERVADO', 'Reservado'),
    ('PRESTADO', 'Prestado'),
    ('EN_REPARACION', 'En reparación'),
    ('PERDIDO', 'Perdido'),
    ('BAJA', 'Baja'),
]

# Estados que el bibliotecario puede poner a mano
ESTADOS_MANUALES = [e for e in ESTADOS if e[0] in ('DISPONIBLE', 'EN_REPARACION', 'PERDIDO', 'BAJA')]

# RESERVADO y PRESTADO los controla el sistema con los préstamos
ESTADOS_DEL_SISTEMA = ('RESERVADO', 'PRESTADO')

PRESTAMOS_EN_CURSO = ['SOLICITADO', 'ACTIVO', 'VENCIDO']


# Revisa si el ejemplar está ligado a un préstamo en curso
def tiene_prestamo_en_curso(ejemplar):
    return Prestamo.objects.filter(ejemplar=ejemplar, estado__in=PRESTAMOS_EN_CURSO).exists()


# El estado no se puede cambiar a mano si lo controla un préstamo
def estado_bloqueado(ejemplar):
    return ejemplar.estado in ESTADOS_DEL_SISTEMA or tiene_prestamo_en_curso(ejemplar)


# Formulario de alta y edición de ejemplares (CU-18)
class EjemplarForm(forms.Form):
    isbn = forms.CharField(
        label='ISBN del libro', max_length=20,
        help_text='10 o 13 dígitos, con o sin guiones. El libro debe estar registrado.',
    )
    cantidad = forms.IntegerField(
        label='Cantidad de copias', min_value=1, max_value=20, required=False, initial=1,
        help_text='Para dar de alta varias copias a la vez (el código se genera solo).',
    )
    codigo_inventario = forms.CharField(
        label='Código de inventario', max_length=30, required=False,
        help_text='Déjalo vacío para generarlo automáticamente.',
    )
    ubicacion = forms.CharField(label='Ubicación', max_length=50, required=False,
                                help_text='Estante o sección.')
    estado = forms.ChoiceField(label='Estado', choices=ESTADOS_MANUALES, initial='DISPONIBLE')
    fecha_adquisicion = forms.DateField(
        label='Fecha de adquisición', required=False,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )
    observaciones = forms.CharField(label='Observaciones', max_length=255, required=False)

    def __init__(self, *args, instance=None, libro_inicial=None, **kwargs):
        self.instance = instance
        self.libro = None

        if 'initial' not in kwargs:
            if instance is not None:
                kwargs['initial'] = {
                    'isbn': instance.libro.isbn,
                    'codigo_inventario': instance.codigo_inventario,
                    'ubicacion': instance.ubicacion or '',
                    'estado': instance.estado,
                    'fecha_adquisicion': instance.fecha_adquisicion,
                    'observaciones': instance.observaciones or '',
                }
            else:
                kwargs['initial'] = {
                    'estado': 'DISPONIBLE',
                    'fecha_adquisicion': timezone.localdate(),
                    'cantidad': 1,
                    'isbn': libro_inicial.isbn if libro_inicial else '',
                }

        super().__init__(*args, **kwargs)

        if instance is not None:
            # El libro no se cambia al editar y la cantidad solo aplica al crear
            self.fields['isbn'].disabled = True
            del self.fields['cantidad']
            self.fields['codigo_inventario'].help_text = ''

            if estado_bloqueado(instance):
                self.fields['estado'].choices = ESTADOS
                self.fields['estado'].disabled = True
                self.fields['estado'].help_text = (
                    'Lo controla el sistema porque hay un préstamo en curso con este ejemplar.'
                )

        for campo in self.fields.values():
            if isinstance(campo.widget, forms.Select):
                clase = 'form-select'
            else:
                clase = 'form-control'
            campo.widget.attrs.setdefault('class', clase)

    def clean_isbn(self):
        if self.instance is not None:
            self.libro = self.instance.libro
            return self.instance.libro.isbn

        isbn = re.sub(r'[\s-]', '', self.cleaned_data['isbn'])
        libro = Libro.objects.filter(isbn=isbn).first()

        if libro is None:
            raise forms.ValidationError('No existe un libro con ese ISBN. Regístralo primero en el catálogo.')
        if libro.activo != 1:
            raise forms.ValidationError('Ese libro está dado de baja. Reactívalo antes de agregarle ejemplares.')

        self.libro = libro
        return isbn

    def clean_codigo_inventario(self):
        codigo = self.cleaned_data.get('codigo_inventario', '').strip()

        if codigo:
            existe = Ejemplar.objects.filter(codigo_inventario__iexact=codigo)
            if self.instance is not None:
                existe = existe.exclude(pk=self.instance.pk)
            if existe.exists():
                raise forms.ValidationError('Ya existe un ejemplar con ese código de inventario.')

        return codigo

    def clean(self):
        datos = super().clean()

        if self.instance is not None:
            if not datos.get('codigo_inventario') and 'codigo_inventario' not in self.errors:
                self.add_error('codigo_inventario', 'El código de inventario es obligatorio.')
        else:
            cantidad = datos.get('cantidad') or 1
            if cantidad > 1 and datos.get('codigo_inventario'):
                self.add_error('codigo_inventario',
                               'Con varias copias el código se genera automáticamente; déjalo vacío.')

        return datos

    # Genera un código libre con el formato EJ-<id del libro>-<número>
    @staticmethod
    def _codigo_libre(libro):
        base = f"EJ-{libro.pk:05d}"
        numero = Ejemplar.objects.filter(libro=libro).count() + 1

        while Ejemplar.objects.filter(codigo_inventario=f"{base}-{numero}").exists():
            numero += 1

        return f"{base}-{numero}"

    # Guarda y devuelve la lista de ejemplares creados o actualizados
    @transaction.atomic
    def save(self):
        d = self.cleaned_data

        if self.instance is not None:
            ejemplar = self.instance
            ejemplar.codigo_inventario = d['codigo_inventario']
            ejemplar.ubicacion = d['ubicacion'] or None
            ejemplar.fecha_adquisicion = d['fecha_adquisicion']
            ejemplar.observaciones = d['observaciones'] or None

            if not self.fields['estado'].disabled:
                ejemplar.estado = d['estado']

            ejemplar.save()
            return [ejemplar]

        creados = []
        for _ in range(d.get('cantidad') or 1):
            creados.append(Ejemplar.objects.create(
                libro=self.libro,
                codigo_inventario=d['codigo_inventario'] or self._codigo_libre(self.libro),
                ubicacion=d['ubicacion'] or None,
                estado=d['estado'],
                fecha_adquisicion=d['fecha_adquisicion'],
                observaciones=d['observaciones'] or None,
            ))

        return creados
