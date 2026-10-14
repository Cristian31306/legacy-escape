# Legacy Escape — Cristian Duran & Jorge Ferreira

Documentación oficial del software desarrollado para el reto FESC Legacy Challenge 2026 (Nivel Tecnólogo).

## Descripción

Software de capa de transición y desacoplamiento arquitectónico diseñado para modernizar y liberar el sistema central de afiliados y subsidios de la caja de compensación. Resuelve el acoplamiento directo y de alto riesgo a la base de datos relacional PostgreSQL heredada mediante una API REST Gateway con patrón Adapter. Esta solución permite que el portal de servicios web, la aplicación de subsidios y la aplicación móvil interactúen de forma segura, estandarizada y eficiente sin conocer los nombres, columnas ni códigos internos del esquema legacy, garantizando alta disponibilidad, auditoría continua, resiliencia ante caídas de la base de datos e idempotencia transaccional en operaciones financieras críticas.

## Integrantes

- Cristian Alexander Duran Medina
- Jorge Andres Ferreira Ortega

## Requisitos

Para compilar, desplegar y ejecutar este proyecto se requiere contar con:
- Docker Engine 24.0 o superior
- Docker Compose v2.20 o superior
- Python 3.11 o superior
- Git 2.30 o superior
- Sistema operativo Linux, macOS o Windows 10/11 con WSL2 habilitado

## Instalación y ejecución

Para levantar la infraestructura completa del entorno desde una copia limpia del repositorio, ejecute en orden los siguientes comandos en su terminal:

1. Clonar el repositorio y copiar el archivo de variables de entorno:
   ```bash
   cp .env.example .env
   ```

2. Construir las imágenes e iniciar todos los servicios en segundo plano:
   ```bash
   docker compose up -d --build
   ```

3. Verificar que los contenedores estén saludables y en ejecución:
   ```bash
   docker compose ps
   ```

4. En caso de requerir revertir el estado de migración a la versión anterior de forma inmediata, ejecute:
   ```bash
   ./rollback.sh affiliations
   ```

5. Para detener y limpiar el entorno cuando sea necesario:
   ```bash
   docker compose down
   ```

## Configuración

El archivo `.env` permite configurar el comportamiento de los servicios. Todas las variables se encuentran documentadas en `.env.example`:

- `POSTGRES_DB`: Nombre de la base de datos PostgreSQL legacy a la que se conecta el sistema (ejemplo: `legacy`).
- `POSTGRES_USER`: Usuario administrador para establecer las conexiones con la base de datos (ejemplo: `legacy`).
- `POSTGRES_PASSWORD`: Contraseña de autenticación de la base de datos PostgreSQL (ejemplo: `legacy` o clave segura).
- `LEGACY_DB_HOST`: Nombre de host o resolución DNS del servicio de base de datos dentro de la red Docker (ejemplo: `legacy-db`).
- `LEGACY_DB_PORT`: Puerto TCP expuesto por el motor relacional PostgreSQL (ejemplo: `5432`).
- `GATEWAY_URL`: URL base del servicio Gateway REST para interconexión entre aplicaciones (ejemplo: `http://gateway:8082`).
- `PORTAL_TOKEN`: Token secreto tipo Bearer para autorizar las solicitudes provenientes del portal web (ejemplo: `portal-token`).
- `SUBSIDIOS_TOKEN`: Token secreto tipo Bearer para autorizar el registro de retiros desde la aplicación de subsidios (ejemplo: `subsidios-token`).
- `MOBILE_TOKEN`: Token secreto tipo Bearer para autorizar las consultas de solo lectura desde la app móvil (ejemplo: `mobile-token`).

## Arquitectura

La arquitectura implementa el patrón Strangler Fig (Higo Estrangulador) con una capa de desacoplamiento REST Gateway y un Adapter modular. Los componentes se orquestan en Docker Compose mediante seis servicios interconectados:
- `legacy-db`: Base de datos relacional PostgreSQL heredada que almacena la información histórica de afiliados, beneficiarios, empresas y movimientos.
- `gateway`: Servicio API REST central construido en FastAPI que encapsula el acceso a datos mediante el adapter, aplica autenticación por tokens Bearer, middleware de auditoría y resiliencia con outbox SQLite local.
- `educacion-app`: Aplicación legacy de educación que continúa consultando la base de datos relacional de forma directa sin requerir modificaciones.
- `portal-client`: Portal web de autoservicio que consume la información canónica de afiliados, empresas y beneficiarios exclusivamente a través del servicio gateway con su token respectivo.
- `subsidios-app`: Servicio de gestión y registro de retiros monetarios, migrado para despachar peticiones a través del gateway con fallback automático a la base legacy.
- `tests`: Contenedor automatizado de pruebas de integración con pytest que valida los contratos, seguridad y salud del sistema.

## Uso

El Gateway expone las siguientes rutas REST cumpliendo con el contrato canónico:

1. **Salud del sistema:**
   ```bash
   curl -X GET http://localhost:8082/health
   ```

2. **Consulta canónica de afiliado:**
   ```bash
   curl -X GET http://localhost:8082/api/v1/members/{document} \
     -H "Authorization: Bearer portal-token"
   ```

3. **Consulta de beneficiarios asociados:**
   ```bash
   curl -X GET http://localhost:8082/api/v1/members/{document}/beneficiaries \
     -H "Authorization: Bearer portal-token"
   ```

4. **Consulta de información de empresa:**
   ```bash
   curl -X GET http://localhost:8082/api/v1/companies/{id} \
     -H "Authorization: Bearer portal-token"
   ```

5. **Registro de retiros de afiliados (idempotente):**
   ```bash
   curl -X POST http://localhost:8082/api/v1/members/{document}/retirements \
     -H "Authorization: Bearer subsidios-token" \
     -H "Content-Type: application/json" \
     -d '{"requestId": "req-001", "date": "2026-10-14", "reason": "Retiro voluntario"}'
   ```

6. **Estado de migración por dominios:**
   ```bash
   curl -X GET http://localhost:8082/api/v1/migration/status \
     -H "Authorization: Bearer portal-token"
   ```

## Pruebas

La suite de pruebas automatizadas ejecuta 12 casos de prueba de integración que validan el cumplimiento estricto de los contratos REST, seguridad por roles de token, formato uniforme de errores `{message, error_id}`, idempotencia transaccional y resistencia a fallas. Para ejecutarlas en un contenedor aislado se corre:

```bash
docker compose --profile test run --rm tests
```

El resultado genera el reporte estandarizado JUnit XML en `test-results/junit.xml`.

## Documentación

El repositorio cuenta con documentación técnica detallada en los siguientes archivos:
- [docs/architecture.md](docs/architecture.md): Documento de arquitectura de software, modelo canónico y decisiones técnicas.
- [docs/dependency-map.md](docs/dependency-map.md): Matriz de dependencias y criticidad de aplicaciones sobre el esquema relacional.
- [docs/migration-plan.md](docs/migration-plan.md): Plan de migración por dominios, criterios cuantitativos de avance y rollback.
- [openapi.yaml](openapi.yaml): Contrato OpenAPI 3.0 con la especificación completa de esquemas y endpoints.
- [AI_USAGE.md](AI_USAGE.md): Registro transparente de casos de uso de inteligencia artificial y correcciones del equipo.

## Qué resolvimos

Desacoplamos completamente el modelo relacional heredado sin interrumpir la operación continua del negocio ni afectar a servicios críticos como Educación. Resolvimos la dependencia directa de Subsidios enrutando los retiros por el Gateway, implementamos un Adapter dinámico que tolera cambios de esquema en caliente (`AFI_MAE` vs `person_master`), diseñamos tolerancia a caídas de la base mediante una cola Outbox en SQLite local que reintenta sin duplicidad y garantizamos idempotencia transaccional en operaciones financieras.

## Limitaciones y pendientes

La migración completa del dominio de aportes empresariales y la desincorporación definitiva del procedimiento almacenado legacy quedan programadas para la fase de modernización total del backend.
