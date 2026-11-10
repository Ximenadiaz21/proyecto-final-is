
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth.views import LoginView, LogoutView

from cuentas.views import panel_usuario


urlpatterns = [
    # Abre el administrador
    path('admin/', admin.site.urls),

    # Manda la página principal al login
    path('', RedirectView.as_view(
        pattern_name='login',
        permanent=False
    ), name='inicio'),

    # Permite iniciar sesión
    path('login/', LoginView.as_view(
        template_name='login.html',
        redirect_authenticated_user=True
    ), name='login'),

    # Permite cerrar sesión
    path('logout/', LogoutView.as_view(
        next_page='login'
    ), name='logout'),

    # Muestra el panel del usuario
    path('panel/', panel_usuario, name='panel'),

    # Conecta el catálogo de libros
    path('catalogo/', include('catalogo.urls')),
]
