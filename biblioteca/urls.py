from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)

from cuentas.views import (
    panel_usuario,
    mis_notificaciones,
    marcar_notificacion_leida,
    marcar_todas_leidas,
)
from cuentas.views_sugerencias import (
    mis_sugerencias,
    gestion_sugerencias,
    responder_sugerencia,
)
from prestamos.views_reportes import reportes


urlpatterns = [
    # Abre el administrador
    path('admin/', admin.site.urls),

    # Manda la página principal al login
    path('', RedirectView.as_view(
        pattern_name='login',
        permanent=False
    ), name='inicio'),

    # Permite iniciar sesión (CU-01)
    path('login/', LoginView.as_view(
        template_name='login.html',
        redirect_authenticated_user=True
    ), name='login'),

    # Permite cerrar sesión (CU-02)
    path('logout/', LogoutView.as_view(
        next_page='login'
    ), name='logout'),

    # Recuperación de contraseña por correo (CU-03)
    path('recuperar-contrasena/', PasswordResetView.as_view(
        template_name='cuentas/password_reset_form.html',
        email_template_name='cuentas/password_reset_email.html',
        subject_template_name='cuentas/password_reset_subject.txt',
    ), name='password_reset'),
    path('recuperar-contrasena/enviado/', PasswordResetDoneView.as_view(
        template_name='cuentas/password_reset_done.html',
    ), name='password_reset_done'),
    path('recuperar-contrasena/<uidb64>/<token>/', PasswordResetConfirmView.as_view(
        template_name='cuentas/password_reset_confirm.html',
    ), name='password_reset_confirm'),
    path('recuperar-contrasena/completado/', PasswordResetCompleteView.as_view(
        template_name='cuentas/password_reset_complete.html',
    ), name='password_reset_complete'),

    # Muestra el panel del usuario
    path('panel/', panel_usuario, name='panel'),

    # Notificaciones del usuario (CU-15)
    path('notificaciones/', mis_notificaciones, name='mis_notificaciones'),
    path('notificaciones/<int:notificacion_id>/leer/', marcar_notificacion_leida, name='marcar_notificacion_leida'),
    path('notificaciones/leer-todas/', marcar_todas_leidas, name='marcar_todas_leidas'),

    # Sugerencias de adquisición de libros (CU-16, CU-33)
    path('sugerencias/', mis_sugerencias, name='mis_sugerencias'),
    path('sugerencias/gestion/', gestion_sugerencias, name='gestion_sugerencias'),
    path('sugerencias/<int:sugerencia_id>/responder/', responder_sugerencia, name='responder_sugerencia'),

    # Reportes operativos de la biblioteca (CU-32, RF-14)
    path('reportes/', reportes, name='reportes'),

    # Conecta el catálogo de libros
    path('catalogo/', include('catalogo.urls')),

    # Conecta los préstamos
    path('prestamos/', include('prestamos.urls')),
    # Conecta las multas y pagos
    path('multas/', include('multas.urls')),
    # Conecta la gestión de usuarios
    path('usuarios/', include('cuentas.urls')),
    # Conecta la gestión de ejemplares
    path('ejemplares/', include('catalogo.urls_ejemplares')),
]