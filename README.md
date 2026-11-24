# Sistema de Gestión de Biblioteca Escolar

Proyecto final de Ingeniería de Software. Aplicación web desarrollada con **Python 3.12+**, **Django 5.2** y **MySQL 8** (InnoDB, `utf8mb4`) que automatiza la operación completa de una biblioteca escolar: catálogo, préstamos en línea y mostrador, devoluciones, reservas en cola FIFO, cálculo y cobro de multas, sugerencias de adquisición, notificaciones y reportes operativos.

## Requisitos

- Python 3.12 o superior
- MySQL 8.x (motor InnoDB, codificación `utf8mb4`)
- Git
- En Windows, `mysqlclient` suele instalarse con rueda precompilada mediante `pip`.

## Instalación

1. **Clona el repositorio y entra a la carpeta**

   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd proyecto-final-is
   ```

2. **Crea y activa el entorno virtual**

   ```powershell
   python -m venv venv
   venv\Scripts\activate          # Windows (PowerShell)
   # source venv/bin/activate     # Linux / macOS
   ```

3. **Instala las dependencias**

   ```bash
   pip install -r requirements.txt
   ```

4. **Crea la base de datos vacía en MySQL**

   ```sql
   CREATE DATABASE biblioteca CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

   > Si vas a ejecutar `python manage.py test`, asegúrate de que el usuario de MySQL tenga permisos para crear la base temporal `test_biblioteca`.

5. **Configura las variables de entorno**

   Copia `.env.example` como `.env` y coloca tus credenciales locales de MySQL:

   ```powershell
   copy .env.example .env         # Windows
   # cp .env.example .env         # Linux / macOS
   ```

   - Las credenciales **no** se suben al repositorio (`.env` está en `.gitignore`).
   - El correo electrónico (CU-03 y RF-15) imprime en consola por defecto; para enviar correos reales por SMTP, configura `EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD` en `.env`.

6. **Aplica las migraciones**

   ```bash
   python manage.py migrate
   ```

   Esto crea las 18 tablas del modelo entidad-relación, las restricciones `CHECK`/`UNIQUE`/`PROTECT`, el grupo de permisos `Bibliotecarios` y las políticas de préstamo iniciales (`ESTUDIANTE` y `PROFESOR`).

7. **Carga los datos de prueba**

   ```bash
   python manage.py usuarios
   python manage.py libros
   python manage.py demo_operacion
   ```

   - `usuarios`: crea **20 estudiantes**, **5 profesores**, **2 bibliotecarios**, 5 carreras y 5 departamentos.
   - `libros`: carga **50 libros** con **100 ejemplares** (consulta OpenLibrary si hay conexión, o usa datos locales con `--offline`).
   - `demo_operacion` *(opcional, idempotente)*: carga préstamos de demostración (devueltos, activos, solicitados y vencidos), reservas en cola FIFO, multas, pagos, sugerencias y notificaciones para probar reportes desde el inicio.
   - También puedes crear un administrador manualmente con `python manage.py createsuperuser` (solicita usuario, correo y tipo de usuario).

8. **Inicia el servidor**

   ```bash
   python manage.py runserver
   ```

   Abre <http://127.0.0.1:8000>.

## Usuarios de prueba

Todos los usuarios generados por `python manage.py usuarios` comparten la contraseña `passbiblio`:

| Rol | Usuarios | Cantidad |
|---|---|---|
| Bibliotecario | `bibliotecario_demo`, `bibliotecario02` | 2 |
| Profesor | `profesor01` a `profesor05` | 5 |
| Estudiante | `alumno01` a `alumno20` | 20 |

## Comandos útiles

| Comando | Descripción |
|---|---|
| `python manage.py usuarios` | Carga carreras, departamentos y 27 usuarios de prueba (idempotente). |
| `python manage.py libros [--offline]` | Carga 50 libros y 100 ejemplares en el catálogo (idempotente). |
| `python manage.py demo_operacion` | Carga operación de demostración para reportes y flujos (idempotente). |
| `python manage.py procesar_vencimientos` | Marca préstamos vencidos (CU-34), expira solicitudes/reservas (CU-35) y envía recordatorios (CU-36). |
| `python manage.py procesar_vencimientos --dry-run` | Simula el proceso programado sin modificar la base de datos. |
| `python manage.py test` | Ejecuta las **55 pruebas automatizadas** (reglas RN-01 a RN-16, permisos, flujos y reportes). |
| `python manage.py check` | Verifica la configuración del proyecto Django. |

El comando `procesar_vencimientos` está diseñado para ejecutarse diariamente desde el Programador de tareas de Windows o `cron` (RF-17).

## Estructura del proyecto

```text
proyecto-final-is/
├── manage.py
├── requirements.txt
├── .env.example
├── biblioteca/     # configuración (settings, urls, wsgi, backend SMTP)
├── cuentas/        # Usuario, Estudiante, Profesor, Carrera, Departamento, Notificacion, SugerenciaAdquisicion, permisos y notificaciones
├── catalogo/       # Autor, Editorial, Categoria, Libro, LibroAutor, Ejemplar y búsqueda
├── prestamos/      # PoliticaPrestamo, Prestamo, Reserva, reglas, capa de servicios y comandos programados
├── multas/         # Multa, Pago y capa de servicios de cobro/condonación
├── reportes/       # Reportes operativos por periodo y exportación CSV (sin modelos)
├── templates/      # Plantillas HTML responsivas (Bootstrap 5, incluye 403.html y 404.html)
└── static/         # Estilos CSS personalizados
```

## Reglas de negocio principales

Los parámetros de RN-01 a RN-06 se almacenan en la tabla `politica_prestamo` y son editables desde la aplicación sin modificar código (CU-31):

| Regla | Descripción | Estudiante | Profesor |
|---|---|---:|---:|
| RN-01 | Días de préstamo (naturales) | 7 | 30 |
| RN-02 | Máximo de libros simultáneos | 3 | 10 |
| RN-03 | Renovaciones permitidas por préstamo | 1 | 2 |
| RN-04 | Multa por día de retraso | $10.00 MXN | $10.00 MXN |
| RN-05 | Multa máxima por préstamo | $300.00 MXN | $300.00 MXN |
| RN-06 | Horas para recoger solicitud o reserva | 48 h | 48 h |

- **RN-07:** `monto = min(días_retraso × multa_por_día, multa_máxima)`.
- **RN-08 a RN-16:** elegibilidad sin adeudos/vencidos, bloqueo de renovación ante vencimiento o reservas, cola FIFO al liberar ejemplares, multas por daño/pérdida según `costo_reposicion`, condonación exclusiva de bibliotecario con justificación obligatoria, bloqueo de ejemplares no prestables y conservación histórica sin borrado físico.

## Tecnologías

Python 3.12+ · Django 5.2 · MySQL 8 · Bootstrap 5.3 · Bootstrap Icons
