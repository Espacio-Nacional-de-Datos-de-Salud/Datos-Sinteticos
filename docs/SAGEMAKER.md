# Guía AWS SageMaker

Esta guía detalla el proceso paso a paso para configurar tu entorno de desarrollo en AWS, desde la solicitud de acceso hasta la gestión de almacenamiento y costes.

## 📂 Documentación de Referencia

Antes de empezar, ten a mano estos enlaces oficiales del departamento:

* [Carpeta General de Manuales](https://www.google.com/search?q=https://everisgroup.sharepoint.com/sites/businessanalytics/3%2520Herramientas/Forms/AllItems.aspx%3Fid%3D%252Fsites%252Fbusinessanalytics%252F3%2520Herramientas%252F2%2520AWS%2520BA%252F2%2520Manuales%2520de%2520usuario)
* [Estructura de S3 (Subida de archivos)](https://www.google.com/search?q=https://everisgroup.sharepoint.com/:w:/r/sites/businessanalytics/_layouts/15/Doc.aspx%3Fsourcedoc%3D%257B833266DE-50C4-43CB-A285-09A9ACE7CDF0%257D%26file%3DS3%2520-%2520Subida%2520de%2520archivos.docx)
* [Video Tutorial de Setup (Reunión completa)](https://www.google.com/search?q=https://everisgroup.sharepoint.com/:v:/s/businessanalytics/IQC2ynh55alJQ7IVeBgfRgUOAZsa6VzV63ZzGcFZJ356xb0)


## 1. Solicitud de Acceso

Lo primero es obtener los permisos necesarios. No podrás ver la cuenta en el portal si no completas este paso.

[AWS BA - Acceso 2025](https://www.google.com/search?q=https://everisgroup.sharepoint.com/:w:/r/sites/businessanalytics/_layouts/15/Doc.aspx%3Fsourcedoc%3D%257BE6A6B7E5-83C0-4446-97BA-1CCA2B07C567%257D%26file%3DAWS%2520BA%2520-%2520Acceso%25202025.docx).

## 2. Configuración del Perfil en AWS SageMaker

Una vez tengas el acceso confirmado, sigue estos pasos para entrar al entorno:

### Acceso al Portal

1. Entra en el **Access Portal de AWS**: [AWS](https://awsitnegociobilling.awsapps.com/start/#/?tab=accounts).
2. Despliega la pestaña de la cuenta **Proyecto_PrcessMining**.
3. Haz clic en **DefaultProjectAccess**.

### Creación del User Profile

1. En la consola de AWS, busca el servicio **Amazon SageMaker AI**.
2. **IMPORTANTE:** Asegúrate de que la región seleccionada (arriba a la derecha) sea **eu-west-1 (Irlanda)**.
3. En el menú lateral izquierdo, ve a **Admin configurations** > **Domains**.
4. Entra en el único dominio disponible.
5. Ve a la pestaña **User profiles** y haz clic en **Add user**.
6. **Nombre del perfil:** Usa el formato `{usuario_ntt}-{codigo proyecto leible, libertad de elegir realmente}` (Ejemplo: `obustosm-pt5`).
7. **Ajustes obligatorios:**
* Asegura que **MLflow** y **Docker** estén habilitados.
* **Costes:** Configura el **Idle time** (tiempo de inactividad) al valor mínimo posible. Esto apagará las instancias si se te olvida hacerlo manualmente.


## 3. Entorno de Desarrollo: Code Editor

SageMaker Studio permite usar Jupyter, VS Code y MLflow. Para desarrollo estándar, lo ideal es crear un **Code Editor Space**.

* **¿Qué es?** Un espacio que contiene tu código, datos y repositorios.
* **Instancia de Cómputo:** Selecciona la adecuada para tu proyecto. Recuerda que se cobra por tiempo encendido, no por carga de CPU. Nosotros lo que hacemos es crear dos Code Editors, uno grande para entrenso serios, y uno pequeño para desarrollar con pruebas más ligeras. Es interesante coger la serie ml.m* para el primer caso, éstas rinden el 100% del tiempo con las especificaciones que elijas, y la serie ml.t* para el segundo caso, que es más barata pero no rinde al 100% del tiempo, sino que se adapta a la carga de trabajo, durante tiempos que no se está suando la CPU acumula "créditos" que luego puede usar para rendir al 100% durante un tiempo limitado. Si corremos cargas intensas mucho tiempo, se gastan los créditos y el rendimiento baja.

* **Almacenamiento (Storage):** Se monta en tu `/home`.
> ⚠️ **¡Atención!** El almacenamiento se cobra **siempre**, incluso si el espacio está apagado. No crees espacios excesivamente grandes ni tengas varios sin usar.


## 4. Configuración de Git

Para evitar introducir tus credenciales (Usuario + PAT de GitLab/GitHub) cada vez que hagas un push o pull, ejecuta el siguiente comando en la terminal de SageMaker o de tu VS Code local:

```bash
git config --global user.email "you@example.com"
git config --global user.name "Your Name"
```

```bash
git config --global credential.helper store

```

*La próxima vez que introduzcas tus datos, se guardarán permanentemente en el entorno.*

---

## 5. Gestión de Almacenamiento y Datos

### Monitorizar espacio en disco

Es vital vigilar el espacio en `/home/sagemaker-user`, ya que si se llena, el entorno puede fallar.
Para ver el estado actual, usa:

```bash
df -h
```
Esto mostrará algo como:

```
Filesystem Size Used Avail Use% Mounted on

overlay 37G 144K 37G 1% /

tmpfs 64M 0 64M 0% /dev

/dev/nvme0n1p1 180G 88G 93G 49% /opt/.sagemakerinternal

/dev/nvme1n1 20G 15G 5.2G 75% /home/sagemaker-user

```

Hay que fijarse en el Mounted on home/sagemaker-user, que es donde se guardan tus archivos. En nuestro caso las dependencias son pesadas, y con lo que necesita el studio de base para funcionar, con 10gb ya llenamos el espacio. Harán falta almenos +20gb para trabajar cómodamente.

### Carga de datos desde S3

Para copiar datos de un bucket (por ejemplo, datos sintéticos de Synthea) a tu entorno local en SageMaker:

```bash
aws s3 cp --no-sign-request --recursive s3://synthea-omop/synthea1k/ ./synthea1k/

```
