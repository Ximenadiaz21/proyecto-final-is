import os
import ssl
import sys

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPEmailBackend
from django.utils.functional import cached_property


# Backend SMTP con validación TLS activa por defecto y respaldo en consola si la red bloquea el puerto (CU-03, RF-15).
class SMTPEmailBackend(DjangoSMTPEmailBackend):

    @cached_property
    def ssl_context(self):
        contexto = ssl.create_default_context()
        # Solo permite omitir verificación de certificado si se activa explícitamente en desarrollo local
        inseguro = os.environ.get('EMAIL_INSECURE_SSL', 'False').strip().lower() in ('true', '1', 'yes', 'si')
        if inseguro:
            contexto.check_hostname = False
            contexto.verify_mode = ssl.CERT_NONE
        return contexto

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        try:
            enviados = super().send_messages(email_messages)
            destinatarios = [', '.join(m.to) for m in email_messages]
            sys.stdout.write(
                f"\n[SMTP OK] Correo enviado realmente a: {'; '.join(destinatarios)}\n"
            )
            sys.stdout.flush()
            return enviados
        except Exception as error:
            sys.stdout.write(
                f"\n[Aviso SMTP] No se pudo enviar por red ({error}). "
                f"Mostrando el correo en consola como respaldo:\n"
            )
            sys.stdout.flush()
            return ConsoleEmailBackend().send_messages(email_messages)
