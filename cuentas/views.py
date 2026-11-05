
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


# Muestra el panel principal de la biblioteca.
@login_required
def panel(request):

    # Obtén los datos del usuario que inició sesión.
    usuario = request.user

    # Envía el usuario a la plantilla del panel.
    return render(request, 'panel.html', {
        'usuario': usuario
    })
