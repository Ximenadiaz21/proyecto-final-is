import csv
import io
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from .forms import UsuarioForm
from .models import Usuario, Carrera, Departamento

MAX_FILAS_CSV = 500
MAX_BYTES_CSV = 1_000_000
COLUMNAS_CSV = [
    'username', 'nombre', 'apellidos', 'correo', 'tipo', 'matricula',
    'carrera', 'semestre', 'num_empleado', 'departamento', 'password',
]
COLUMNAS_OBLIGATORIAS = {'username', 'nombre', 'apellidos', 'correo', 'tipo'}


# Deja pasar solo a bibliotecarios que no estén bloqueados
def bibliotecario_requerido(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if request.user.tipo_usuario != 'BIBLIOTECARIO' or request.user.bloqueado:
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return login_required(envoltura)


# Lista los usuarios con buscador, filtros y paginación (CU-20)
@bibliotecario_requerido
def gestion_usuarios(request):
    busqueda = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '')
    estado = request.GET.get('estado', '')

    usuarios = Usuario.objects.select_related(
        'estudiante__carrera', 'profesor__departamento'
    ).order_by('username')

    if busqueda:
        usuarios = usuarios.filter(
            Q(username__icontains=busqueda) |
            Q(first_name__icontains=busqueda) |
            Q(last_name__icontains=busqueda) |
            Q(email__icontains=busqueda) |
            Q(estudiante__matricula__icontains=busqueda) |
            Q(profesor__num_empleado__icontains=busqueda)
        )

    if tipo in dict(Usuario.TIPO_CHOICES):
        usuarios = usuarios.filter(tipo_usuario=tipo)

    if estado == 'bloqueados':
        usuarios = usuarios.filter(bloqueado=True)
    elif estado == 'activos':
        usuarios = usuarios.filter(bloqueado=False)

    pagina = Paginator(usuarios, 15).get_page(request.GET.get('page'))

    # Agrega el identificador y el detalle del perfil a cada usuario de la página
    for u in pagina:
        estudiante = getattr(u, 'estudiante', None)
        profesor = getattr(u, 'profesor', None)
        if estudiante:
            u.identificador = estudiante.matricula
            u.detalle_perfil = f"{estudiante.carrera.nombre} · semestre {estudiante.semestre}"
        elif profesor:
            u.identificador = profesor.num_empleado
            u.detalle_perfil = profesor.departamento.nombre
        else:
            u.identificador = ''
            u.detalle_perfil = ''

    parametros = request.GET.copy()
    parametros.pop('page', None)

    contexto = {
        'usuario': request.user,
        'titulo': 'Gestión de usuarios',
        'pagina': pagina,
        'busqueda': busqueda,
        'tipo': tipo,
        'estado': estado,
        'tipos': Usuario.TIPO_CHOICES,
        'querystring': parametros.urlencode(),
    }

    return render(request, 'usuarios/gestion_usuarios.html', contexto)


# Da de alta un usuario
@bibliotecario_requerido
def nuevo_usuario(request):
    datos = request.POST if request.method == 'POST' else None
    form = UsuarioForm(datos)

    if request.method == 'POST' and form.is_valid():
        creado = form.save()
        messages.success(request, f"Usuario {creado.username} creado correctamente.")
        return redirect('gestion_usuarios')

    contexto = {
        'usuario': request.user,
        'titulo': 'Nuevo usuario',
        'form': form,
        'editando': None,
    }
    return render(request, 'usuarios/formulario_usuario.html', contexto)


# Edita los datos de un usuario existente
@bibliotecario_requerido
def editar_usuario(request, usuario_id):
    editando = get_object_or_404(Usuario, id=usuario_id)
    datos = request.POST if request.method == 'POST' else None
    form = UsuarioForm(datos, instance=editando)

    if request.method == 'POST' and form.is_valid():
        guardado = form.save()
        messages.success(request, f"Usuario {guardado.username} actualizado correctamente.")
        return redirect('gestion_usuarios')

    contexto = {
        'usuario': request.user,
        'titulo': 'Editar usuario',
        'form': form,
        'editando': editando,
    }
    return render(request, 'usuarios/formulario_usuario.html', contexto)


# Bloquea o desbloquea a un usuario (CU-22)
@bibliotecario_requerido
@require_POST
def cambiar_bloqueo(request, usuario_id):
    objetivo = get_object_or_404(Usuario, id=usuario_id)

    if objetivo.pk == request.user.pk:
        messages.error(request, "No puedes bloquear tu propia cuenta.")
        return redirect('gestion_usuarios')

    if objetivo.bloqueado:
        objetivo.bloqueado = False
        objetivo.motivo_bloqueo = None
        objetivo.save(update_fields=['bloqueado', 'motivo_bloqueo'])
        messages.success(request, f"Usuario {objetivo.username} desbloqueado.")
        return redirect('gestion_usuarios')

    motivo = request.POST.get('motivo', '').strip()

    if not motivo:
        messages.error(request, "Escribe el motivo del bloqueo.")
        return redirect('gestion_usuarios')

    if len(motivo) > 255:
        messages.error(request, "El motivo no puede pasar de 255 caracteres.")
        return redirect('gestion_usuarios')

    objetivo.bloqueado = True
    objetivo.motivo_bloqueo = motivo
    objetivo.save(update_fields=['bloqueado', 'motivo_bloqueo'])
    messages.success(request, f"Usuario {objetivo.username} bloqueado.")
    return redirect('gestion_usuarios')


# Descarga un CSV de ejemplo para la carga masiva
@bibliotecario_requerido
def plantilla_csv(request):
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = 'attachment; filename="plantilla_usuarios.csv"'
    respuesta.write('\ufeff')

    escritor = csv.writer(respuesta)
    escritor.writerow(COLUMNAS_CSV)
    escritor.writerow(['a00000001', 'Ana', 'López Pérez', 'ana.lopez@ejemplo.mx', 'ESTUDIANTE',
                       'A00000001', 'SIS', '3', '', '', ''])
    escritor.writerow(['prof_ejemplo', 'Luis', 'Gómez Ruiz', 'luis.gomez@ejemplo.mx', 'PROFESOR',
                       '', '', '', 'PROF1001', 'Ingeniería', ''])
    return respuesta


# Convierte los bytes del archivo en texto (acepta UTF-8 y archivos de Excel en español)
def _decodificar(archivo):
    contenido = archivo.read()
    for codificacion in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return contenido.decode('utf-8', errors='replace')


# Junta los errores de un formulario en una sola frase
def _errores_texto(form):
    partes = []
    for campo, errores in form.errors.items():
        nombre = form.fields[campo].label if campo in form.fields else 'General'
        partes.append(f"{nombre}: {' '.join(errores)}")
    return ' | '.join(partes)


# Procesa el CSV fila por fila. Devuelve (resultados, mensaje_de_error)
def _procesar_csv(archivo):
    texto = _decodificar(archivo)

    try:
        dialecto = csv.Sniffer().sniff(texto[:2048], delimiters=',;')
    except csv.Error:
        dialecto = csv.excel

    lector = csv.DictReader(io.StringIO(texto), dialect=dialecto)

    if not lector.fieldnames:
        return [], "El archivo está vacío."

    lector.fieldnames = [(c or '').strip().lower() for c in lector.fieldnames]
    faltantes = COLUMNAS_OBLIGATORIAS - set(lector.fieldnames)
    if faltantes:
        return [], "Faltan columnas obligatorias: " + ', '.join(sorted(faltantes)) + "."

    resultados = []

    for numero, fila in enumerate(lector, start=2):
        if len(resultados) >= MAX_FILAS_CSV:
            return resultados, f"Se procesaron las primeras {MAX_FILAS_CSV} filas; el resto se ignoró."

        fila = {k: (v or '').strip() for k, v in fila.items() if k}
        if not any(fila.values()):
            continue

        resultado = {'fila': numero, 'username': fila.get('username', ''), 'ok': False,
                     'detalle': '', 'password': ''}

        # Busca la carrera por clave y el departamento por nombre
        carrera = departamento = None
        if fila.get('carrera'):
            carrera = Carrera.objects.filter(clave__iexact=fila['carrera']).first()
            if carrera is None:
                resultado['detalle'] = f"La carrera '{fila['carrera']}' no existe."
                resultados.append(resultado)
                continue

        if fila.get('departamento'):
            departamento = Departamento.objects.filter(nombre__iexact=fila['departamento']).first()
            if departamento is None:
                resultado['detalle'] = f"El departamento '{fila['departamento']}' no existe."
                resultados.append(resultado)
                continue

        # Si no trae contraseña se genera una al azar
        password = fila.get('password', '')
        generada = not password
        if generada:
            password = get_random_string(10)

        datos = {
            'username': fila.get('username', ''),
            'password': password,
            'first_name': fila.get('nombre', ''),
            'last_name': fila.get('apellidos', ''),
            'email': fila.get('correo', ''),
            'telefono': fila.get('telefono', ''),
            'tipo_usuario': fila.get('tipo', '').upper(),
            'matricula': fila.get('matricula', ''),
            'carrera': carrera.pk if carrera else '',
            'semestre': fila.get('semestre', ''),
            'num_empleado': fila.get('num_empleado', ''),
            'departamento': departamento.pk if departamento else '',
        }

        form = UsuarioForm(datos)

        if not form.is_valid():
            resultado['detalle'] = _errores_texto(form)
        else:
            try:
                form.save()
                resultado['ok'] = True
                resultado['detalle'] = 'Usuario creado'
                resultado['password'] = password if generada else ''
            except Exception as error:
                resultado['detalle'] = f"No se pudo guardar: {error}"

        resultados.append(resultado)

    return resultados, ''


# Carga masiva de usuarios desde un CSV (CU-21)
@bibliotecario_requerido
def importar_usuarios(request):
    contexto = {
        'usuario': request.user,
        'titulo': 'Importar usuarios',
        'columnas': COLUMNAS_CSV,
        'resultados': None,
    }

    if request.method == 'POST':
        archivo = request.FILES.get('archivo')

        if not archivo:
            messages.error(request, "Selecciona un archivo CSV.")
        elif archivo.size > MAX_BYTES_CSV:
            messages.error(request, "El archivo es muy grande (máximo 1 MB).")
        else:
            resultados, aviso = _procesar_csv(archivo)

            if aviso:
                messages.warning(request, aviso)

            contexto['resultados'] = resultados
            contexto['creados'] = sum(1 for r in resultados if r['ok'])
            contexto['fallidos'] = sum(1 for r in resultados if not r['ok'])
            contexto['con_password'] = any(r['password'] for r in resultados)

    return render(request, 'usuarios/importar_usuarios.html', contexto)
