
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


# Muestra el panel del usuario
@login_required
def panel_usuario(request):

    # Obtén el usuario que inició sesión
    usuario = request.user

    # Revisa el tipo de usuario
    if usuario.tipo_usuario == 'ESTUDIANTE':
        titulo = 'Panel del estudiante'

    elif usuario.tipo_usuario == 'PROFESOR':
        titulo = 'Panel del profesor'

    elif usuario.tipo_usuario == 'BIBLIOTECARIO':
        titulo = 'Panel del bibliotecario'

    else:
        titulo = 'Panel de usuario'

    # Envía los datos al HTML
    contexto = {
        'usuario': usuario,
        'titulo': titulo,
    }

    return render(request, 'panel.html', contexto)
