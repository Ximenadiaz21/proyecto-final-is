from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from catalogo.models import Libro, Ejemplar
from .models import PoliticaPrestamo, Prestamo
from multas.models import Multa

@login_required
def solicitar_prestamo(request, libro_id):
    libro = get_object_or_404(Libro, id=libro_id, activo=1)
    usuario = request.user

    # 1. Validar que el usuario sea Estudiante o Profesor
    if usuario.tipo_usuario not in ['ESTUDIANTE', 'PROFESOR']:
        messages.error(request, "Los bibliotecarios no pueden solicitar préstamos.")
        return redirect('lista_libros')

    # 2. Validar si el usuario está bloqueado o tiene multas pendientes / préstamos vencidos (RN-08)
    if usuario.bloqueado:
        messages.error(request, "Tu cuenta está bloqueada. No puedes solicitar préstamos.")
        return redirect('lista_libros')
    
    tiene_multas = Multa.objects.filter(usuario=usuario, estado='PENDIENTE').exists()
    prestamos_vencidos = Prestamo.objects.filter(usuario=usuario, estado='VENCIDO').exists()
    
    if tiene_multas or prestamos_vencidos:
        messages.error(request, "No puedes solicitar libros porque tienes multas pendientes o préstamos vencidos (RN-08).")
        return redirect('lista_libros')

    # 3. Obtener política de préstamo según el tipo de usuario (RN-01 a RN-05)[cite: 1]
    try:
        politica = PoliticaPrestamo.objects.get(tipo_usuario=usuario.tipo_usuario)
    except PoliticaPrestamo.DoesNotExist:
        messages.error(request, "No hay una política de préstamo configurada para tu tipo de usuario.")
        return redirect('lista_libros')

    # 4. Validar límite máximo de libros simultáneos (RN-02)[cite: 1]
    prestamos_activos = Prestamo.objects.filter(
        usuario=usuario, 
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).count()

    if prestamos_activos >= politica.max_libros:
        messages.error(request, f"Has alcanzado el límite máximo de libros permitidos ({politica.max_libros})[cite: 1].")
        return redirect('lista_libros')

    # 5. Validar que el usuario no tenga ya un préstamo activo de este mismo título (RN-11)[cite: 1]
    mismo_titulo_activo = Prestamo.objects.filter(
        usuario=usuario,
        ejemplar__libro=libro,
        estado__in=['SOLICITADO', 'ACTIVO', 'VENCIDO']
    ).exists()

    if mismo_titulo_activo:
        messages.error(request, "Ya tienes un préstamo activo o solicitado de este mismo título (RN-11)[cite: 1].")
        return redirect('lista_libros')

    # 6. Transacción atómica para asignar ejemplar disponible de forma segura (RNF-03)[cite: 1]
    with transaction.atomic():
        ejemplar_disponible = Ejemplar.objects.select_for_update().filter(
            libro=libro, 
            estado='DISPONIBLE'
        ).first()

        if not ejemplar_disponible:
            messages.error(request, "Lo sentimos, ya no quedan ejemplares disponibles de este libro.")
            return redirect('lista_libros')

        # Cambiar estado del ejemplar a RESERVADO / apartado para recoger
        ejemplar_disponible.estado = 'RESERVADO'
        ejemplar_disponible.save()

        # Calcular fecha límite para recoger (RN-06)[cite: 1]
        ahora = timezone.now()
        limite_recoger = ahora + timezone.timedelta(hours=politica.horas_para_recoger)

        # Crear el registro del préstamo en estado SOLICITADO
        Prestamo.objects.create(
            usuario=usuario,
            ejemplar=ejemplar_disponible,
            estado='SOLICITADO',
            fecha_solicitud=ahora,
            fecha_limite_recoger=limite_recoger,
            num_renovaciones=0
        )

        messages.success(request, f"¡Solicitud exitosa! Acércate a recoger el ejemplar [{ejemplar_disponible.codigo_inventario}] antes de {limite_recoger.strftime('%d/%m/%Y %H:%M')}.")
    
    return redirect('panel')