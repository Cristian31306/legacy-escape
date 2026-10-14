# Uso de inteligencia artificial

## Uso 1
- Herramienta: Antigravity IDE (Gemini 3.8 Flash)
- Para qué se usó: Detección dinámica del esquema de base de datos en el Adapter ante el evento de cambio de nombres
- Prompt principal (resumido): "Diseña un mecanismo en Python con psycopg2 que inspeccione information_schema para consultar person_master o afi_mae sin reiniciar el servicio"
- Qué produjo: Una función que consultaba el esquema una sola vez al iniciar la aplicación y lo cacheaba en una variable estática global.
- Qué modificó o corrigió el equipo: Eliminamos el cache estático rígido para que la resolución consulte la existencia de la tabla en tiempo de ejecución, permitiendo adaptarse en caliente tras ejecutar schema-change.sh sin requerir reinicio del servicio.

## Uso 2
- Herramienta: Antigravity IDE (Gemini 3.8 Flash)
- Para qué se usó: Diseño de resiliencia con patrón Outbox e idempotencia ante caídas del motor PostgreSQL
- Prompt principal (resumido): "Implementa una cola local resiliente con SQLite para almacenar peticiones de retiro cuando la base de datos principal arroje timeout"
- Qué produjo: Un script que guardaba los retiros en un archivo JSON plano en disco y reintentaba mediante un ciclo while bloqueante.
- Qué modificó o corrigió el equipo: Reemplazamos el archivo JSON por una base de datos SQLite transaccional con tabla outbox y worker en un hilo daemon desacoplado, asegurando persistencia ACID y previniendo pérdidas de retiros durante caídas del legacy.

## Uso 3
- Herramienta: ChatGPT (GPT-4o)
- Para qué se usó: Identificación de dependencias y criticidad entre aplicaciones legacy y tablas relacionales
- Prompt principal (resumido): "Analiza los procesos de Educación, Subsidios y Reportes e infiere las operaciones de lectura o escritura sobre AFI_MAE, EMPRESA y LOGMOV"
- Qué produjo: Una matriz de dependencias que incluía también al nuevo Gateway y a servicios inexistentes con criticidad alta.
- Qué modificó o corrigió el equipo: Filtramos las aplicaciones nuevas siguiendo las reglas del reto (el calificador penaliza dependencias ficticias o del gateway), dejando únicamente las 6 dependencias históricas reales con su nivel exacto de criticidad.

## Uso 4
- Herramienta: Antigravity IDE (Gemini 3.8 Flash)
- Para qué se usó: Implementación del script de rollback para revertir el dominio Afiliaciones a estado LEGACY
- Prompt principal (resumido): "Crea un script rollback.sh en bash que reciba el dominio affiliations y actualice el estado a LEGACY cumpliendo con códigos de salida Unix"
- Qué produjo: Un script que dependía de curl para llamar al endpoint del gateway y modificar variables de entorno en tiempo de ejecución.
- Qué modificó o corrigió el equipo: Modificamos el script para que manipule directamente el archivo de estado JSON compartido con cat EOF, garantizando una reversión inmediata en menos de 2 segundos sin depender de que el servicio HTTP esté levantado.
