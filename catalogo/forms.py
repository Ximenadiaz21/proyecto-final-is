
from django import forms
from django.core.validators import RegexValidator

from .models import Libro, Autor, Editorial, Categoria


# Formulario para registrar y editar los libros de la biblioteca
class LibroForm(forms.ModelForm):

    # Permite seleccionar un autor registrado en la base de datos
    autor = forms.ModelChoiceField(
        queryset=Autor.objects.all().order_by('apellidos', 'nombre'),
        label='Autor',
        empty_label='Seleccionar autor',
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    class Meta:
        model = Libro

        # Campos que el bibliotecario puede modificar
        fields = [
            'isbn',
            'titulo',
            'subtitulo',
            'editorial',
            'categoria',
            'anio_publicacion',
            'edicion',
            'idioma',
            'num_paginas',
            'descripcion',
            'portada',
            'costo_reposicion',
        ]

        labels = {
            'isbn': 'ISBN',
            'titulo': 'Título',
            'subtitulo': 'Subtítulo',
            'editorial': 'Editorial',
            'categoria': 'Categoría',
            'anio_publicacion': 'Año de publicación',
            'edicion': 'Edición',
            'idioma': 'Idioma',
            'num_paginas': 'Número de páginas',
            'descripcion': 'Descripción',
            'portada': 'URL de la portada',
            'costo_reposicion': 'Costo de reposición',
        }

        widgets = {
            'isbn': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ISBN de 10 o 13 dígitos',
            }),
            'titulo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Título del libro',
            }),
            'subtitulo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subtítulo (opcional)',
            }),
            'editorial': forms.Select(attrs={
                'class': 'form-select',
            }),
            'categoria': forms.Select(attrs={
                'class': 'form-select',
            }),
            'anio_publicacion': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
            }),
            'edicion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Primera edición',
            }),
            'idioma': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Español',
            }),
            'num_paginas': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Descripción del libro',
            }),
            'portada': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://...',
            }),
            'costo_reposicion': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'step': '0.01',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Muestra los nombres completos de los autores
        self.fields['autor'].label_from_instance = (
            lambda autor: f'{autor.nombre} {autor.apellidos}'
        )

        # Ordena las editoriales y categorías alfabéticamente
        self.fields['editorial'].queryset = Editorial.objects.order_by('nombre')
        self.fields['categoria'].queryset = Categoria.objects.order_by('nombre')


        # Muestra el nombre real de cada editorial
        self.fields['editorial'].label_from_instance = (
            lambda editorial: editorial.nombre
        )

        # Muestra el nombre real de cada categoría
        self.fields['categoria'].label_from_instance = (
            lambda categoria: categoria.nombre
        )


        # Cuando se edita un libro, selecciona su primer autor registrado
        if self.instance and self.instance.pk:
            relacion = self.instance.libroautor_set.order_by('orden').first()

            if relacion:
                self.fields['autor'].initial = relacion.autor

    def clean_isbn(self):

        # Elimina los guiones y espacios para guardar el ISBN uniforme
        isbn = self.cleaned_data['isbn'].replace('-', '').replace(' ', '')

        if not isbn.isdigit() or len(isbn) not in (10, 13):
            raise forms.ValidationError(
                'El ISBN debe contener 10 o 13 dígitos.'
            )

        return isbn

    
# Formulario para registrar nuevos autores
class AutorForm(forms.ModelForm):

    class Meta:
        model = Autor

        fields = [
            'nombre',
            'apellidos',
            'nacionalidad',
        ]

        labels = {
            'nombre': 'Nombre',
            'apellidos': 'Apellidos',
            'nacionalidad': 'Nacionalidad',
        }

        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Antoine',
            }),
            'apellidos': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. de Saint-Exupéry',
            }),
            'nacionalidad': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Francesa',
            }),
        }

    # Evita registrar dos veces al mismo autor (excluyendo el propio al editar)
    def clean(self):
        datos = super().clean()

        nombre = datos.get('nombre')
        apellidos = datos.get('apellidos')

        if nombre and apellidos:
            consulta = Autor.objects.filter(
                nombre__iexact=nombre.strip(),
                apellidos__iexact=apellidos.strip()
            )
            if self.instance and self.instance.pk:
                consulta = consulta.exclude(pk=self.instance.pk)

            if consulta.exists():
                raise forms.ValidationError(
                    'Este autor ya está registrado en la biblioteca.'
                )

        return datos


# Formulario para registrar nuevas editoriales
class EditorialForm(forms.ModelForm):

    class Meta:
        model = Editorial

        fields = ['nombre', 'pais']

        labels = {
            'nombre': 'Nombre de la editorial',
            'pais': 'País',
        }

        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Salamandra',
            }),
            'pais': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. España',
            }),
        }

    # Evita registrar dos editoriales con el mismo nombre (excluyendo la propia al editar)
    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()

        consulta = Editorial.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)

        if consulta.exists():
            raise forms.ValidationError(
                'Esta editorial ya está registrada.'
            )

        return nombre


# Formulario para registrar nuevas categorías
class CategoriaForm(forms.ModelForm):

    class Meta:
        model = Categoria

        fields = ['nombre', 'descripcion']

        labels = {
            'nombre': 'Nombre de la categoría',
            'descripcion': 'Descripción',
        }

        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Literatura clásica',
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe los libros de esta categoría',
            }),
        }

    # Evita registrar dos categorías con el mismo nombre (excluyendo la propia al editar)
    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()

        consulta = Categoria.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)

        if consulta.exists():
            raise forms.ValidationError(
                'Esta categoría ya está registrada.'
            )

        return nombre

