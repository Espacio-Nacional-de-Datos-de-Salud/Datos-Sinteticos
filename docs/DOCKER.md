# Docker
Docker proporciona una forma sencilla de lograr portabilidad e aislamiento del código. Un contenedor de Docker es más ligero que una máquina virtual completa, ya que utiliza el mismo núcleo (kernel) del host, pero implementa su propio sistema operativo, llamado contenedor. Este contenedor se inicia a partir de una imagen, la cual se crea mediante las instrucciones incluidas en un Dockerfile. Al usar Docker, se garantiza una ejecución consistente en diferentes entornos.

## Forma del Dockerfile
Nuestro Dockerfile utiliza un proceso de construcción de dos etapas (2-stage build) para reducir el tamaño de la imagen. Sin embargo, debido al gran tamaño de nuestras dependencias, el tamaño total de la imagen sigue siendo considerable, alrededor de 8 GB. Esta imagen de Docker contiene únicamente los requisitos para entrenamiento y simulación (requirements_core.txt) y, por lo tanto, no puede utilizarse para evaluación. Esto se debe a que el plan actual es dejar de usar synthcity para evitar el mantenimiento de dos entornos separados.

### Etapa 1 (Builder)
Base: python:3.12.3-slim-bookworm

Instala uv (gestor de paquetes de Python rápido).

Crea un entorno virtual en /opt/venv.

Instala las dependencias desde requirements_core.txt.

### Etapa 2 (Final)
Misma imagen base pero con un inicio limpio.

Copia el entorno virtual pre-construido desde la etapa de builder.

Configura las variables de entorno y copia el código de la aplicación desde el repositorio local.

Ejecuta "python -m src.main" como usuario no-root.

El archivo .dockerignore define los archivos y directorios que Docker no debe copiar al contenedor al ejecutar COPY . .

Dado que los datos tabulares con los que trabajaremos son bastante grandes, no deben copiarse dentro del contenedor. En su lugar, pueden montarse, ya sea a través de un parámetro de línea de comandos en docker run o como se define en el archivo de configuración de Docker Compose. Esto permite que el contenedor acceda a archivos específicos en la máquina host.

## Uso en AWS SageMaker
Al ejecutar comandos de Docker como docker build o docker run, se debe incluir la opción --network sagemaker; de lo contrario, el comando fallará. Si decides utilizar la extensión Container Tools, puedes actualizar el archivo de configuración para incluir automáticamente esta opción al usar la interfaz gráfica (GUI).

Ejemplo:

/home/sagemaker-user/sagemaker-code-editor-server-data/data/User/settings.json
```
{
    "containers.commands.build": "${containerCommand} build --network sagemaker --pull --rm -f \"$  {dockerfile}\" -t ${tag} \"${context}\"",
    "containers.commands.runInteractive": "${containerCommand} run --network sagemaker --rm -it ${exposedPorts} ${tag}",
    "containers.commands.run": "${containerCommand} run --network sagemaker --rm -d ${exposedPorts} ${tag}"
}
```

Esta opción se incluye en todos los comandos de este archivo; sin embargo, debe eliminarse si se ejecuta en un entorno diferente (por ejemplo, localmente).

## Ejemplo de uso
Estando en el repositorio, puedes usar el comando:

```
docker build --network sagemaker -t ds:1.0.0 .
```
para construir la imagen. La opción -t define la etiqueta (tag) de la imagen, en este caso ds (datos sintéticos) versión 1.0.0. Una nota importante es que, si se construyen varias imágenes, cada una debe tener una etiqueta diferente. Docker no advertirá sobre el uso de la misma etiqueta, pero esto afectará la caché y resultará en tamaños de imagen mayores. El número de versión puede simplemente incrementarse en cada construcción para evitar esto.

Actualmente, el programa se ejecuta de forma interactiva en la línea de comandos. Por lo tanto, el contenedor de Docker debe ejecutarse en modo interactivo. Esto se logra mediante el comando:

```
docker run --network sagemaker --rm -it ds:1.0.0
```
reemplazando ds:1.0.0 por la etiqueta que hayas utilizado. Alternativamente, si usas la extensión Container Tools, puedes hacer clic derecho en el nombre de la imagen y seleccionar "Run Interactively".

## Docker Compose
Una vez que la API de la aplicación esté configurada, el método preferido será utilizar Docker Compose. Esto permitirá omitir los procesos manuales de construcción y ejecución simplemente corriendo "docker compose up", asegurando un inicio consistente. Docker Compose también facilitará la conexión entre la interfaz de usuario (UI) y el backend, los cuales se ejecutarán en contenedores separados.

Sin embargo, Docker Compose no está diseñado para utilizarse con aplicaciones de línea de comandos, por lo que su uso debe posponerse hasta que la API sea funcional.

## MLflow
Actualmente, no se ha investigado el uso de un servidor de MLflow externo para Docker. Por lo tanto, MLflow se ejecutará automáticamente en modo local dentro del contenedor, almacenando allí todos los metadatos. Estos se eliminarán al finalizar la ejecución del programa. Esto podría solucionarse configurando un volumen, lo que permitiría que los experimentos realizados dentro de Docker se guarden localmente en la máquina host.

## Ejemplo volumen
```
docker run --network sagemaker --rm -it -v /home/sagemaker-user/herramienta-datos-sinteticos/data:/app/data ds:1.0.0
```