from django.shortcuts import render

def inicio_requerimientos(request):
    return render(request, 'requerimientos.html')