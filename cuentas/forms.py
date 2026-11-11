from django import forms
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction

from .models import Usuario, Estudiante, Profesor, Carrera, Departamento


# Formulario de alta y edición de usuarios (con su perfil de estudiante o profesor)
class UsuarioForm(forms.Form):
    username = forms.CharField(
        label='Usuario', max_length=150,
        validators=[UnicodeUsernameValidator()],
    )
    password = forms.CharField(
        label='Contraseña', required=False, min_length=8,
        widget=forms.PasswordInput(render_value=False),
    )
    first_name = forms.CharField(label='Nombre', max_length=150)
    last_name = forms.CharField(label='Apellidos', max_length=150)
    email = forms.EmailField(label='Correo', max_length=254)
    telefono = forms.CharField(label='Teléfono', max_length=20, required=False)
    tipo_usuario = forms.ChoiceField(label='Tipo de usuario', choices=Usuario.TIPO_CHOICES)

    # Datos del estudiante
    matricula = forms.CharField(label='Matrícula', max_length=20, required=False)
    carrera = forms.ModelChoiceField(
        label='Carrera', queryset=Carrera.objects.order_by('nombre'), required=False,
        empty_label='Selecciona una carrera',
    )
    semestre = forms.IntegerField(label='Semestre', min_value=1, max_value=20, required=False)

    # Datos del profesor
    num_empleado = forms.CharField(label='Número de empleado', max_length=20, required=False)
    departamento = forms.ModelChoiceField(
        label='Departamento', queryset=Departamento.objects.order_by('nombre'), required=False,
        empty_label='Selecciona un departamento',
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance

        if instance is not None and 'initial' not in kwargs:
            kwargs['initial'] = self._initial_desde(instance)

        super().__init__(*args, **kwargs)

        if instance is not None:
            # El tipo de usuario no se cambia al editar, para no dejar perfiles huérfanos
            self.fields['tipo_usuario'].disabled = True
            self.fields['password'].help_text = 'Déjala vacía para conservar la contraseña actual.'
        else:
            self.fields['password'].label = 'Contraseña inicial'
            self.fields['password'].help_text = 'Mínimo 8 caracteres.'

        for campo in self.fields.values():
            clase = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'
            campo.widget.attrs.setdefault('class', clase)

    @staticmethod
    def _initial_desde(usuario):
        inicial = {
            'username': usuario.username,
            'first_name': usuario.first_name,
            'last_name': usuario.last_name,
            'email': usuario.email,
            'telefono': usuario.telefono or '',
            'tipo_usuario': usuario.tipo_usuario,
        }

        estudiante = Estudiante.objects.filter(usuario=usuario).first()
        if estudiante:
            inicial.update(
                matricula=estudiante.matricula,
                carrera=estudiante.carrera_id,
                semestre=estudiante.semestre,
            )

        profesor = Profesor.objects.filter(usuario=usuario).first()
        if profesor:
            inicial.update(
                num_empleado=profesor.num_empleado,
                departamento=profesor.departamento_id,
            )

        return inicial

    # Agrupa los campos para dibujarlos por secciones en la plantilla
    @property
    def bloque_cuenta(self):
        nombres = ('username', 'password', 'first_name', 'last_name', 'email', 'telefono', 'tipo_usuario')
        return [self[n] for n in nombres]

    @property
    def bloque_estudiante(self):
        return [self[n] for n in ('matricula', 'carrera', 'semestre')]

    @property
    def bloque_profesor(self):
        return [self[n] for n in ('num_empleado', 'departamento')]

    def _excluir_propio(self, consulta, campo_usuario=None):
        if self.instance is None:
            return consulta
        if campo_usuario:
            return consulta.exclude(**{campo_usuario: self.instance.pk})
        return consulta.exclude(pk=self.instance.pk)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        existe = self._excluir_propio(Usuario.objects.filter(username__iexact=username))
        if existe.exists():
            raise forms.ValidationError('Ya existe un usuario con ese nombre de usuario.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        existe = self._excluir_propio(Usuario.objects.filter(email__iexact=email))
        if existe.exists():
            raise forms.ValidationError('Ya existe un usuario con ese correo.')
        return email

    def clean(self):
        datos = super().clean()
        tipo = datos.get('tipo_usuario')

        # La contraseña es obligatoria solo al crear
        if self.instance is None and not datos.get('password') and 'password' not in self.errors:
            self.add_error('password', 'Escribe una contraseña inicial.')

        if tipo == 'ESTUDIANTE':
            for campo in ('matricula', 'carrera', 'semestre'):
                if not datos.get(campo):
                    self.add_error(campo, 'Este dato es obligatorio para estudiantes.')

            matricula = datos.get('matricula')
            if matricula:
                existe = self._excluir_propio(
                    Estudiante.objects.filter(matricula__iexact=matricula), 'usuario_id'
                )
                if existe.exists():
                    self.add_error('matricula', 'Ya existe un estudiante con esa matrícula.')

        elif tipo == 'PROFESOR':
            for campo in ('num_empleado', 'departamento'):
                if not datos.get(campo):
                    self.add_error(campo, 'Este dato es obligatorio para profesores.')

            numero = datos.get('num_empleado')
            if numero:
                existe = self._excluir_propio(
                    Profesor.objects.filter(num_empleado__iexact=numero), 'usuario_id'
                )
                if existe.exists():
                    self.add_error('num_empleado', 'Ya existe un profesor con ese número de empleado.')

        return datos

    # Guarda el usuario y su perfil en una sola transacción
    @transaction.atomic
    def save(self):
        d = self.cleaned_data

        usuario = self.instance or Usuario(tipo_usuario=d['tipo_usuario'])
        usuario.username = d['username']
        usuario.first_name = d['first_name']
        usuario.last_name = d['last_name']
        usuario.email = d['email']
        usuario.telefono = d['telefono'] or None

        if d.get('password'):
            usuario.set_password(d['password'])

        if self.instance is None:
            usuario.is_active = True
            usuario.bloqueado = False

        usuario.save()

        if usuario.tipo_usuario == 'ESTUDIANTE':
            estudiante = Estudiante.objects.filter(usuario=usuario).first()
            if estudiante:
                estudiante.matricula = d['matricula']
                estudiante.carrera = d['carrera']
                estudiante.semestre = d['semestre']
                estudiante.save()
            else:
                Estudiante.objects.create(
                    usuario=usuario, matricula=d['matricula'],
                    carrera=d['carrera'], semestre=d['semestre'],
                )

        elif usuario.tipo_usuario == 'PROFESOR':
            profesor = Profesor.objects.filter(usuario=usuario).first()
            if profesor:
                profesor.num_empleado = d['num_empleado']
                profesor.departamento = d['departamento']
                profesor.save()
            else:
                Profesor.objects.create(
                    usuario=usuario, num_empleado=d['num_empleado'],
                    departamento=d['departamento'],
                )

        return usuario
