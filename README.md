# proyecto-final-is
# Sistema de Gestión de Biblioteca Escolar

Proyecto final de Ingeniería de Software. Aplicación web hecha con **Django 5.2** y **MySQL 8** que automatiza la operación de una biblioteca escolar: catálogo, préstamos, devoluciones, multas y administración.

## Requisitos

- Python 3.12 o superior
- MySQL 8.x (motor InnoDB, `utf8mb4`)
- Git
- En Windows, `mysqlclient` suele instalarse sin compilar con `pip`. Si falla, instala una versión con rueda precompilada.

## Instalación

1. **Clona el repositorio y entra a la carpeta**

   ```
   git clone <URL_DEL_REPOSITORIO>
   cd proyecto-final-is
   ```

2. **Crea y activa el entorno virtual**

   ```
   python -m venv venv
   venv\Scripts\activate          # Windows (PowerShell)
   source venv/bin/activate       # Linux / macOS
   ```

3. **Instala las dependencias**

   ```
   pip install -r requirements.txt
   ```

4. **Crea la base de datos vacía en MySQL**

   ```sql
   CREATE DATABASE biblioteca CHARACTER SET utf8mb4;
   ```

5. **Configura las variables de entorno**

   Copia `.env.example` como `.env` y escribe tu usuario y contraseña de MySQL:

   ```
   copy .env.example .env         # Windows
   cp .env.example .env           # Linux / macOS
   ```

   Las credenciales no se suben al repositorio: `.env` está en `.gitignore`.

6. **Crea las tablas**

   ```
   python manage.py migrate
   ```

   Esto crea todas las tablas y las dos políticas de préstamo iniciales (Estudiante y Profesor).

7. **Carga los datos de prueba**

   ```
   python manage.py usuarios
   python manage.py libros
   ```

   - `usuarios`: crea estudiantes, profesores y bibliotecario.
   - `libros`: carga 50 libros con 100 ejemplares. Consulta OpenLibrary, así que necesita conexión a internet y tarda más de un minuto.

8. **Inicia el servidor**

   ```
   python manage.py runserver
   ```

   Abre <http://127.0.0.1:8000>.

## Usuarios de prueba

| Rol | Usuario | Contraseña |
|---|---|---|
| Bibliotecario | `<USUARIO_BIBLIOTECARIO>` | `<CONTRASEÑA>` |
| Profesor | `<USUARIO_PROFESOR>` | `<CONTRASEÑA>` |
| Estudiante | `<USUARIO_ESTUDIANTE>` | `<CONTRASEÑA>` |

> Sustituye los valores entre `< >` con los que genera el comando `usuarios`.

## Comandos útiles

| Comando | Qué hace |
|---|---|
| `python manage.py procesar_vencimientos` | Marca préstamos vencidos, expira solicitudes y reservas no recogidas, y envía recordatorios (CU-34, CU-35 y CU-36). |
| `python manage.py procesar_vencimientos --dry-run` | Muestra lo que haría sin guardar cambios. |
| `python manage.py test` | Ejecuta las pruebas automatizadas. |
| `python manage.py check` | Verifica la configuración del proyecto. |

El comando `procesar_vencimientos` está pensado para ejecutarse una vez al día (por ejemplo con el Programador de tareas de Windows o `cron`).

## Estructura del proyecto

```
proyecto-final-is/
├── manage.py
├── requirements.txt
├── .env.example
├── biblioteca/     # configuración (settings, urls)
├── cuentas/        # Usuario, Estudiante, Profesor, Notificacion, gestión de usuarios
├── catalogo/       # Autor, Editorial, Categoria, Libro, Ejemplar
├── prestamos/      # PoliticaPrestamo, Prestamo, Reserva y reglas de negocio
├── multas/         # Multa, Pago
└── templates/      # plantillas HTML (Bootstrap 5)
```

## Reglas de negocio principales

Los valores predeterminados están en la tabla `politica_prestamo` y se modifican sin cambiar código.

| Regla | Estudiante | Profesor |
|---|---|---|
| Días de préstamo | 7 | 30 |
| Libros simultáneos | 3 | 10 |
| Renovaciones | 1 | 2 |
| Multa por día de retraso | $10.00 MXN | $10.00 MXN |
| Multa máxima por préstamo | $300.00 MXN | $300.00 MXN |
| Horas para recoger | 48 | 48 |

La multa por retraso se calcula como `min(días_retraso × multa_por_día, multa_máxima)`.

## Tecnologías

Python · Django 5.2 · MySQL 8 · Bootstrap 5.3 · Bootstrap Icons