# Compatibilidad hacia atrás: la lógica vive ahora en la app dedicada `reportes`.
from reportes.views import exportar_reporte_csv, reportes  # noqa: F401
