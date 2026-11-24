"""Capa de servicios de dominio para préstamos y reservas (RNF-06, RNF-03).

Centraliza todas las reglas de negocio (RN-01 a RN-16) dentro de transacciones
atómicas con bloqueo de filas (select_for_update), completamente desacopladas
de la capa HTTP (no reciben request ni hacen redirect).
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalogo.models import Ejemplar
from cuentas.models import Notificacion, Usuario
from cuentas.servicios import notificar
from multas.models import Multa
from .models import PoliticaPrestamo, Prestamo, Reserva
from .reglas import (
    liberar_o_asignar_ejemplar,
    libros_en_uso,
    motivo_inelegible,
    motivo_no_renovable,
)


class ReglaNegocioError(Exception):
    """Excepción de dominio lanzada al infringir una regla de negocio (RN-01 a RN-16)."""

    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        # Código opcional para que la vista decida a qué pantalla redirigir
        self.codigo = codigo


# Recupera la política activa según el rol del lector (ESTUDIANTE o PROFESOR)
def _obtener_politica(tipo_usuario):
    try:
        return PoliticaPrestamo.objects.get(tipo_usuario=tipo_usuario)
    except PoliticaPrestamo.DoesNotExist:
        raise ReglaNegocioError(
            "No hay una política de préstamo configurada para este tipo de usuario."
        )


# CU-06: Solicitar préstamo de libro en línea (RN-01, RN-02, RN-06, RN-08, RN-11, RN-15)
@transaction.atomic
def solicitar_prestamo(usuario_id, libro):
    # Bloquea la fila del usuario para serializar solicitudes simultáneas del mismo lector
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)

    # 1. Solo lectores activos (estudiantes y profesores) pueden solicitar préstamos
    if usuario.tipo_usuario not in ('ESTUDIANTE', 'PROFESOR'):
        raise ReglaNegocioError("Los bibliotecarios no pueden solicitar préstamos.")

    if not usuario.is_active:
        raise ReglaNegocioError("Tu cuenta no está activa. Contacta al personal de la biblioteca.")

    # 2. Elegibilidad: cuenta sin bloqueo, sin multas pendientes y sin vencidos (CU-07, RN-08)
    motivo = motivo_inelegible(usuario)
    if motivo:
        raise ReglaNegocioError(motivo)

    # 3. Obtiene la política vigente del tipo de usuario (RN-01 a RN-06)
    politica = _obtener_politica(usuario.tipo_usuario)

    # 4. Verifica límite máximo de libros simultáneos, contando reservas apartadas (RN-02)
    if libros_en_uso(usuario) >= politica.max_libros:
        raise ReglaNegocioError(
            f"Has alcanzado el límite máximo de libros permitidos ({politica.max_libros}) (RN-02)."
        )

    # 5. Impide tener dos préstamos en curso del mismo título (RN-11)
    if Prestamo.objects.filter(
        usuario=usuario,
        ejemplar__libro=libro,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO'],
    ).exists():
        raise ReglaNegocioError(
            "Ya tienes un préstamo activo o solicitado de este mismo título (RN-11)."
        )

    # 6. Bloquea y selecciona el primer ejemplar DISPONIBLE para evitar doble asignación (RNF-03)
    ejemplar = (
        Ejemplar.objects.select_for_update()
        .filter(libro=libro, estado='DISPONIBLE')
        .first()
    )
    if not ejemplar:
        raise ReglaNegocioError(
            "Ya no quedan ejemplares disponibles de este libro. Puedes reservarlo.",
            codigo='sin_disponibles',
        )

    # 7. Aparta el ejemplar y crea el préstamo en estado SOLICITADO con límite de recogida (RN-06)
    ejemplar.estado = 'RESERVADO'
    ejemplar.save(update_fields=['estado'])

    ahora = timezone.now()
    limite_recoger = ahora + timedelta(hours=politica.horas_para_recoger)
    limite_local = timezone.localtime(limite_recoger)

    prestamo = Prestamo.objects.create(
        usuario=usuario,
        ejemplar=ejemplar,
        estado='SOLICITADO',
        fecha_solicitud=ahora,
        fecha_limite_recoger=limite_recoger,
        num_renovaciones=0,
    )

    # 8. Postcondición de CU-06: genera notificación con folio y plazo de recogida
    notificar(
        usuario=usuario,
        tipo=Notificacion.Tipo.GENERAL,
        mensaje=(
            f"Solicitud #{prestamo.id} de \"{libro.titulo}\" registrada. "
            f"Recoge el ejemplar {ejemplar.codigo_inventario} antes del "
            f"{limite_local:%d/%m/%Y %H:%M}."
        ),
        fecha=ahora,
    )
    return prestamo


# CU-08: Cancelar solicitud de préstamo no recogida (libera o reasigna en cola FIFO RN-12)
@transaction.atomic
def cancelar_solicitud(prestamo_id, usuario):
    # Filtra también por usuario para garantizar aislamiento entre lectores (RNF-02)
    prestamo = Prestamo.objects.select_for_update().get(id=prestamo_id, usuario=usuario)

    if prestamo.estado != 'SOLICITADO':
        raise ReglaNegocioError("Solo se pueden cancelar solicitudes que aún no se han recogido.")

    prestamo.estado = 'CANCELADO'
    prestamo.save(update_fields=['estado'])

    # Libera el ejemplar apartado o lo asigna a la reserva PENDIENTE más antigua (RN-12)
    ejemplar = Ejemplar.objects.select_for_update().select_related('libro').get(
        pk=prestamo.ejemplar_id
    )
    reserva_asignada = None
    if ejemplar.estado == 'RESERVADO':
        reserva_asignada = liberar_o_asignar_ejemplar(ejemplar, timezone.now())

    return prestamo, reserva_asignada


# CU-10: Renovar préstamo activo (RN-03, RN-08, RN-09, RN-10)
@transaction.atomic
def renovar_prestamo(prestamo_id, usuario):
    # Bloquea el préstamo propio para evitar doble renovación concurrente
    prestamo = (
        Prestamo.objects.select_for_update()
        .select_related('ejemplar', 'ejemplar__libro', 'usuario')
        .get(id=prestamo_id, usuario=usuario)
    )
    politica = _obtener_politica(usuario.tipo_usuario)

    # Valida estado ACTIVO, elegibilidad, tope de renovaciones y ausencia de reservas
    motivo = motivo_no_renovable(prestamo, politica)
    if motivo:
        raise ReglaNegocioError(motivo)

    # RN-10: extiende la fecha de vencimiento desde hoy según los días de la política
    nueva_fecha = timezone.localdate() + timedelta(days=politica.dias_prestamo)
    prestamo.num_renovaciones += 1
    prestamo.fecha_vencimiento = nueva_fecha
    prestamo.save(update_fields=['num_renovaciones', 'fecha_vencimiento'])
    return prestamo, nueva_fecha


# CU-23: Entregar préstamo solicitado (SOLICITADO -> ACTIVO; expira si venció RN-06)
@transaction.atomic
def entregar_prestamo(prestamo_id, bibliotecario):
    prestamo = (
        Prestamo.objects.select_for_update()
        .select_related('ejemplar', 'ejemplar__libro', 'usuario')
        .get(id=prestamo_id)
    )

    if prestamo.estado != 'SOLICITADO':
        raise ReglaNegocioError("Este préstamo ya no está en estado solicitado.")

    ahora = timezone.now()

    # RN-06: si el plazo para recoger expiró, marca la solicitud EXPIRADO y libera el ejemplar
    if prestamo.fecha_limite_recoger and prestamo.fecha_limite_recoger < ahora:
        prestamo.estado = 'EXPIRADO'
        prestamo.save(update_fields=['estado'])
        ejemplar_exp = Ejemplar.objects.select_for_update().select_related('libro').get(
            pk=prestamo.ejemplar_id
        )
        if ejemplar_exp.estado == 'RESERVADO':
            liberar_o_asignar_ejemplar(ejemplar_exp, ahora)
        return prestamo, True

    # Bloquea usuario y ejemplar para verificar estado real antes de entregar físicamente
    lector = Usuario.objects.select_for_update().get(pk=prestamo.usuario_id)
    ejemplar = Ejemplar.objects.select_for_update().select_related('libro').get(
        pk=prestamo.ejemplar_id
    )

    if not lector.is_active:
        raise ReglaNegocioError(
            f"No se puede entregar: la cuenta de {lector.username} está dada de baja (inactiva)."
        )

    if ejemplar.estado != 'RESERVADO':
        raise ReglaNegocioError(
            f"No se puede entregar: el ejemplar [{ejemplar.codigo_inventario}] "
            f"está en estado {ejemplar.estado} (RN-15)."
        )

    # Re-verifica elegibilidad al momento de la entrega física (CU-23 <<include>> CU-07)
    motivo = motivo_inelegible(lector)
    if motivo:
        raise ReglaNegocioError(f"No se puede entregar: {motivo}")

    politica = _obtener_politica(lector.tipo_usuario)

    # Pasa el préstamo a ACTIVO con fecha de vencimiento calculada desde hoy (RN-01)
    prestamo.estado = 'ACTIVO'
    prestamo.fecha_prestamo = ahora
    prestamo.fecha_vencimiento = timezone.localdate() + timedelta(days=politica.dias_prestamo)
    prestamo.entregado_por = bibliotecario
    prestamo.save()

    ejemplar.estado = 'PRESTADO'
    ejemplar.save(update_fields=['estado'])

    return prestamo, False


# CU-24: Registrar préstamo directo en mostrador ([*] -> ACTIVO)
@transaction.atomic
def registrar_prestamo_mostrador(username, codigo_inventario, bibliotecario, observaciones=None):
    # 1. Busca y bloquea al lector activo
    lector = Usuario.objects.select_for_update().filter(username=username, is_active=True).first()
    if not lector:
        raise ReglaNegocioError(f"No se encontró un usuario activo con username «{username}».")

    if lector.tipo_usuario not in ('ESTUDIANTE', 'PROFESOR'):
        raise ReglaNegocioError("Solo se pueden prestar libros a estudiantes y profesores.")

    # 2. Verifica elegibilidad (CU-07, RN-08) y política del rol
    motivo = motivo_inelegible(lector)
    if motivo:
        raise ReglaNegocioError(f"No se puede prestar a {lector.username}: {motivo}")

    politica = _obtener_politica(lector.tipo_usuario)

    # 3. Verifica límite máximo de libros simultáneos (RN-02)
    if libros_en_uso(lector) >= politica.max_libros:
        raise ReglaNegocioError(
            f"El usuario {lector.username} alcanzó su límite de libros permitidos "
            f"({politica.max_libros}) (RN-02)."
        )

    # 4. Busca y bloquea el ejemplar físico por código de inventario (RN-15)
    ejemplar = (
        Ejemplar.objects.select_for_update()
        .select_related('libro')
        .filter(codigo_inventario=codigo_inventario)
        .first()
    )
    if not ejemplar or not ejemplar.libro.activo:
        raise ReglaNegocioError(
            f"No existe un ejemplar activo con código «{codigo_inventario}»."
        )

    if ejemplar.estado != 'DISPONIBLE':
        raise ReglaNegocioError(
            f"El ejemplar [{ejemplar.codigo_inventario}] no está disponible "
            f"(estado actual: {ejemplar.estado}) (RN-15)."
        )

    # 5. Impide prestar dos ejemplares del mismo título al mismo usuario (RN-11)
    if Prestamo.objects.filter(
        usuario=lector,
        ejemplar__libro=ejemplar.libro,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO'],
    ).exists():
        raise ReglaNegocioError(
            f"El usuario {lector.username} ya tiene un préstamo activo o solicitado "
            f"de «{ejemplar.libro.titulo}» (RN-11)."
        )

    # 6. Crea el préstamo en estado ACTIVO y marca el ejemplar como PRESTADO
    ahora = timezone.now()
    vencimiento = timezone.localdate() + timedelta(days=politica.dias_prestamo)

    prestamo = Prestamo.objects.create(
        usuario=lector,
        ejemplar=ejemplar,
        estado='ACTIVO',
        fecha_solicitud=ahora,
        fecha_prestamo=ahora,
        fecha_vencimiento=vencimiento,
        num_renovaciones=0,
        entregado_por=bibliotecario,
        observaciones=observaciones,
    )

    ejemplar.estado = 'PRESTADO'
    ejemplar.save(update_fields=['estado'])

    notificar(
        usuario=lector,
        tipo=Notificacion.Tipo.GENERAL,
        mensaje=(
            f"Préstamo #{prestamo.id} de \"{ejemplar.libro.titulo}\" "
            f"({ejemplar.codigo_inventario}) registrado en mostrador. "
            f"Fecha de devolución: {vencimiento:%d/%m/%Y}."
        ),
        fecha=ahora,
    )
    return prestamo


# CU-25 / CU-26: Recibir devolución (genera multa por retraso RN-07 y atiende cola FIFO RN-12)
@transaction.atomic
def recibir_devolucion(prestamo_id, bibliotecario):
    prestamo = (
        Prestamo.objects.select_for_update()
        .select_related('ejemplar', 'ejemplar__libro', 'usuario')
        .get(id=prestamo_id)
    )

    if prestamo.estado not in ('ACTIVO', 'VENCIDO'):
        raise ReglaNegocioError("Este préstamo no está pendiente de devolución.")

    ahora = timezone.now()
    hoy = timezone.localdate()
    dias_retraso = prestamo.dias_retraso(hoy)
    multa = None

    # Flujo alternativo 5a (CU-26): si hay retraso, calcula y genera multa atómicamente
    if dias_retraso > 0:
        politica = _obtener_politica(prestamo.usuario.tipo_usuario)
        monto = prestamo.calcular_multa(politica, hoy)
        if monto > 0:
            multa = Multa.objects.create(
                prestamo=prestamo,
                usuario=prestamo.usuario,
                motivo='RETRASO',
                dias_retraso=dias_retraso,
                monto=monto,
                estado='PENDIENTE',
                fecha_generacion=ahora,
            )
            notificar(
                usuario=prestamo.usuario,
                tipo=Notificacion.Tipo.MULTA,
                mensaje=(
                    f"Se generó una multa de ${monto:.2f} por {dias_retraso} día(s) de retraso "
                    f"en la devolución de \"{prestamo.ejemplar.libro.titulo}\"."
                ),
                fecha=ahora,
            )

    # Cierra el préstamo como DEVUELTO y registra al bibliotecario que recibe
    prestamo.estado = 'DEVUELTO'
    prestamo.fecha_devolucion = ahora
    prestamo.recibido_por = bibliotecario
    prestamo.save()

    # Flujo alternativo 6a (RN-12): asigna el ejemplar a la cola FIFO o lo deja DISPONIBLE
    reserva_asignada = liberar_o_asignar_ejemplar(prestamo.ejemplar, ahora)
    return prestamo, multa, dias_retraso, reserva_asignada


# CU-27: Registrar daño o pérdida del ejemplar prestado y generar multa de reposición (RN-13)
@transaction.atomic
def registrar_incidente_ejemplar(prestamo_id, motivo, bibliotecario, observaciones=''):
    if motivo not in ('DANIO', 'PERDIDA'):
        raise ReglaNegocioError("Debes indicar si el incidente es por daño o por pérdida.")

    prestamo = (
        Prestamo.objects.select_for_update()
        .select_related('ejemplar', 'ejemplar__libro', 'usuario')
        .get(id=prestamo_id)
    )

    if prestamo.estado not in ('ACTIVO', 'VENCIDO'):
        raise ReglaNegocioError("Este préstamo ya no está activo.")

    ahora = timezone.now()
    hoy = timezone.localdate()
    libro = prestamo.ejemplar.libro

    # RN-13: el monto del cargo de reposición debe estar configurado (> $0.00)
    if libro.costo_reposicion <= Decimal('0'):
        raise ReglaNegocioError(
            f"El libro «{libro.titulo}» no tiene un costo de reposición mayor a $0.00. "
            "Configúralo en Gestión de libros antes de registrar el incidente (RN-13)."
        )

    # Si además estaba vencido, genera también la multa por días de retraso (RN-07)
    multa_retraso = None
    dias_retraso = prestamo.dias_retraso(hoy)
    if dias_retraso > 0:
        politica = _obtener_politica(prestamo.usuario.tipo_usuario)
        monto_retraso = prestamo.calcular_multa(politica, hoy)
        if monto_retraso > 0:
            multa_retraso = Multa.objects.create(
                prestamo=prestamo,
                usuario=prestamo.usuario,
                motivo='RETRASO',
                dias_retraso=dias_retraso,
                monto=monto_retraso,
                estado='PENDIENTE',
                fecha_generacion=ahora,
            )

    # Genera la multa adicional por daño o pérdida usando costo_reposicion (RN-13)
    multa_incidente = Multa.objects.create(
        prestamo=prestamo,
        usuario=prestamo.usuario,
        motivo=motivo,
        dias_retraso=0,
        monto=libro.costo_reposicion,
        estado='PENDIENTE',
        fecha_generacion=ahora,
    )

    # Actualiza estados: DANIO entrega el libro a reparación; PERDIDA no fija fecha_devolucion
    if motivo == 'DANIO':
        prestamo.estado = 'DEVUELTO'
        prestamo.fecha_devolucion = ahora
        prestamo.ejemplar.estado = 'EN_REPARACION'
        etiqueta = 'daño'
    else:
        prestamo.estado = 'PERDIDO'
        prestamo.ejemplar.estado = 'PERDIDO'
        etiqueta = 'pérdida'

    prestamo.recibido_por = bibliotecario
    if observaciones:
        prestamo.observaciones = observaciones[:255]
        prestamo.ejemplar.observaciones = observaciones[:255]
    prestamo.save()
    prestamo.ejemplar.save()

    # Detecta si quedaron reservas pendientes sin ningún ejemplar activo que pueda atenderlas
    reservas_sin_ejemplar = (
        Reserva.objects.filter(libro=libro, estado='PENDIENTE').exists()
        and not Ejemplar.objects.filter(
            libro=libro,
            estado__in=['DISPONIBLE', 'RESERVADO', 'PRESTADO', 'EN_REPARACION'],
        ).exists()
    )

    notificar(
        usuario=prestamo.usuario,
        tipo=Notificacion.Tipo.MULTA,
        mensaje=(
            f"Se registró una multa de ${multa_incidente.monto:.2f} por {etiqueta} "
            f"del ejemplar [{prestamo.ejemplar.codigo_inventario}] de \"{libro.titulo}\" (RN-13)."
        ),
        fecha=ahora,
    )
    return prestamo, multa_incidente, multa_retraso, dias_retraso, reservas_sin_ejemplar


# CU-11: Reservar libro sin ejemplares disponibles en cola FIFO (RN-08, RN-11, RN-12)
@transaction.atomic
def reservar_libro(usuario_id, libro):
    # Bloquea al usuario para impedir reservas duplicadas por peticiones simultáneas
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)

    if usuario.tipo_usuario not in ('ESTUDIANTE', 'PROFESOR'):
        raise ReglaNegocioError("Los bibliotecarios no pueden reservar libros.")

    if not usuario.is_active:
        raise ReglaNegocioError("Tu cuenta no está activa. Contacta al personal de la biblioteca.")

    # Verifica elegibilidad dentro de la transacción (CU-07, RN-08)
    motivo = motivo_inelegible(usuario)
    if motivo:
        raise ReglaNegocioError(motivo)

    # Bloquea los ejemplares del título para comprobar disponibilidad de forma atómica
    ejemplares_libro = Ejemplar.objects.select_for_update().filter(libro=libro)
    if ejemplares_libro.filter(estado='DISPONIBLE').exists():
        raise ReglaNegocioError(
            "Este libro sí tiene ejemplares disponibles. Puedes solicitar el préstamo directamente.",
            codigo='hay_disponibles',
        )

    # Evita reservar libros cuyos ejemplares están todos perdidos o dados de baja
    if not ejemplares_libro.filter(estado__in=['PRESTADO', 'RESERVADO', 'EN_REPARACION']).exists():
        raise ReglaNegocioError(
            "Este título no cuenta con ejemplares activos en circulación para poder reservarlo."
        )

    # RN-11: no puede reservar un título que ya tiene prestado o solicitado
    if Prestamo.objects.filter(
        usuario=usuario,
        ejemplar__libro=libro,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO'],
    ).exists():
        raise ReglaNegocioError(
            "Ya tienes un préstamo activo o solicitado de este mismo título (RN-11)."
        )

    # Impide duplicar reservas activas del mismo título para el mismo lector
    if Reserva.objects.filter(
        usuario=usuario,
        libro=libro,
        estado__in=['PENDIENTE', 'DISPONIBLE'],
    ).exists():
        raise ReglaNegocioError(
            "Ya tienes una reserva activa para este libro.",
            codigo='ya_reservado',
        )

    ahora = timezone.now()
    reserva = Reserva.objects.create(
        usuario=usuario,
        libro=libro,
        estado='PENDIENTE',
        fecha_reserva=ahora,
    )

    # Calcula la posición FIFO usando el mismo desempate (fecha_reserva, id) que la asignación
    posicion = (
        Reserva.objects.filter(libro=libro, estado='PENDIENTE')
        .filter(
            Q(fecha_reserva__lt=reserva.fecha_reserva)
            | Q(fecha_reserva=reserva.fecha_reserva, id__lte=reserva.id)
        )
        .count()
    )

    notificar(
        usuario=usuario,
        tipo=Notificacion.Tipo.GENERAL,
        mensaje=(
            f"Reserva #{reserva.id} de \"{libro.titulo}\" registrada en la cola de espera "
            f"(posición {posicion}). Te notificaremos cuando un ejemplar esté disponible."
        ),
        fecha=ahora,
    )
    return reserva, posicion


# CU-12 / CU-30: Cancelar reserva (por el propio lector o por el bibliotecario)
@transaction.atomic
def cancelar_reserva(reserva_id, usuario=None, por_bibliotecario=False):
    # Si cancela el lector, se filtra por usuario para impedir cancelar reservas ajenas (RNF-02)
    filtro = {'id': reserva_id}
    if not por_bibliotecario:
        filtro['usuario'] = usuario

    reserva = (
        Reserva.objects.select_for_update()
        .select_related('ejemplar_asignado', 'ejemplar_asignado__libro', 'usuario', 'libro')
        .get(**filtro)
    )

    if reserva.estado not in ('PENDIENTE', 'DISPONIBLE'):
        raise ReglaNegocioError("Solo se pueden cancelar reservas pendientes o disponibles.")

    ejemplar = reserva.ejemplar_asignado
    ahora = timezone.now()

    reserva.estado = 'CANCELADA'
    reserva.ejemplar_asignado = None
    reserva.save(update_fields=['estado', 'ejemplar_asignado'])

    # Si ya tenía un ejemplar apartado, se reasigna al siguiente en cola FIFO o queda DISPONIBLE
    reserva_siguiente = None
    if ejemplar:
        ejemplar_bloqueado = Ejemplar.objects.select_for_update().select_related('libro').get(
            pk=ejemplar.pk
        )
        reserva_siguiente = liberar_o_asignar_ejemplar(ejemplar_bloqueado, ahora)

    # Si la canceló el bibliotecario, se avisa al lector afectado
    if por_bibliotecario:
        notificar(
            usuario=reserva.usuario,
            tipo=Notificacion.Tipo.GENERAL,
            mensaje=f"Tu reserva de \"{reserva.libro.titulo}\" fue cancelada en biblioteca.",
            fecha=ahora,
        )

    return reserva, reserva_siguiente


# CU-30: Entregar el ejemplar apartado de una reserva DISPONIBLE y crear préstamo ACTIVO
@transaction.atomic
def atender_reserva(reserva_id, bibliotecario):
    reserva = (
        Reserva.objects.select_for_update()
        .select_related('usuario', 'libro', 'ejemplar_asignado')
        .get(id=reserva_id)
    )

    if reserva.estado != 'DISPONIBLE' or not reserva.ejemplar_asignado:
        raise ReglaNegocioError("Esta reserva no tiene un ejemplar disponible para entregar.")

    ahora = timezone.now()

    # RN-06: si el plazo de recogida ya venció, marca EXPIRADA y reasigna el ejemplar
    if reserva.fecha_expiracion and reserva.fecha_expiracion < ahora:
        ejemplar_exp = Ejemplar.objects.select_for_update().select_related('libro').get(
            pk=reserva.ejemplar_asignado_id
        )
        reserva.estado = 'EXPIRADA'
        reserva.save(update_fields=['estado'])
        if ejemplar_exp.estado == 'RESERVADO':
            liberar_o_asignar_ejemplar(ejemplar_exp, ahora)
        return None, reserva, True

    # Bloquea al lector y valida cuenta activa y elegibilidad (CU-07, RN-08)
    lector = Usuario.objects.select_for_update().get(pk=reserva.usuario_id)
    if not lector.is_active:
        raise ReglaNegocioError(
            f"No se puede entregar al usuario {lector.username} porque su cuenta está inactiva."
        )

    motivo = motivo_inelegible(lector)
    if motivo:
        raise ReglaNegocioError(f"No se puede entregar al usuario {lector.username}: {motivo}")

    politica = _obtener_politica(lector.tipo_usuario)

    # Verifica límite RN-02 excluyendo esta misma reserva que se está convirtiendo en préstamo
    if libros_en_uso(lector, excluir_reserva_id=reserva.id) >= politica.max_libros:
        raise ReglaNegocioError(
            f"El usuario {lector.username} ya alcanzó su límite de libros "
            f"({politica.max_libros}) (RN-02)."
        )

    # RN-11: evita entregar un título que el lector ya tenga en préstamo
    if Prestamo.objects.filter(
        usuario=lector,
        ejemplar__libro=reserva.libro,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO'],
    ).exists():
        raise ReglaNegocioError(
            f"El usuario {lector.username} ya tiene un préstamo activo de este título (RN-11)."
        )

    # Confirma que el ejemplar asignado siga efectivamente apartado (RESERVADO)
    ejemplar = Ejemplar.objects.select_for_update().get(pk=reserva.ejemplar_asignado_id)
    if ejemplar.estado != 'RESERVADO':
        raise ReglaNegocioError(
            f"El ejemplar [{ejemplar.codigo_inventario}] no está apartado "
            f"(estado actual: {ejemplar.estado})."
        )

    # Crea el préstamo ACTIVO, marca el ejemplar PRESTADO y cierra la reserva como ATENDIDA
    vencimiento = timezone.localdate() + timedelta(days=politica.dias_prestamo)
    prestamo = Prestamo.objects.create(
        usuario=lector,
        ejemplar=ejemplar,
        estado='ACTIVO',
        fecha_solicitud=reserva.fecha_reserva,
        fecha_prestamo=ahora,
        fecha_vencimiento=vencimiento,
        num_renovaciones=0,
        entregado_por=bibliotecario,
    )

    ejemplar.estado = 'PRESTADO'
    ejemplar.save(update_fields=['estado'])

    reserva.estado = 'ATENDIDA'
    reserva.save(update_fields=['estado'])

    return prestamo, reserva, False
