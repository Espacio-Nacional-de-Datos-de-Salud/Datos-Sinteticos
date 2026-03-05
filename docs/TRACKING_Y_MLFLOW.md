# Seguimiento de experimentos: MLflow y el sistema de tracking

Este documento explica de forma sencilla cómo la herramienta registra y organiza todo lo que ocurre cada vez que se entrena un modelo o se genera un conjunto de datos sintéticos.

---

## ¿Por qué necesitamos un sistema de seguimiento?

Cada vez que ejecutamos la herramienta, pueden cambiar muchas cosas: los datos de entrada, los parámetros de configuración, el número de registros generados, las reglas aplicadas... Sin un sistema de registro, sería imposible responder preguntas como:

- ¿Con qué datos se generó este conjunto sintético?
- ¿Qué configuración se usó en este modelo?
- ¿Cuántas comprobaciones de calidad fallaron en la última simulación?
- ¿Este conjunto sintético se generó antes o después de cambiar las reglas?

El sistema de tracking resuelve exactamente eso: **deja huella de todo automáticamente**, sin que nadie tenga que hacer nada extra.

---

## El diario de a bordo: qué se guarda en cada ejecución

La herramienta distingue dos tipos de ejecución, y en cada una guarda información diferente.

### Cuando se entrena un modelo

Al entrenar, se crea una carpeta con nombre `modelo_YYYYMMDD_HHMMSS` (fecha y hora exacta) dentro de `outputs/models/`. Dentro de esa carpeta se guarda:

| Archivo | Qué contiene |
|---|---|
| `model_card.json` | Identificador del modelo, fecha, y una huella digital (SHA-256) de cada fichero de datos de entrada |
| `metadata.json` | Descripción de las tablas y columnas utilizadas |
| `generator.zip` | El modelo entrenado, listo para generar datos |
| `rule_manager.pkl` | Las reglas lógicas aplicadas durante el entrenamiento |
| `train.log` | El registro completo de todo lo que ocurrió durante el entrenamiento |
| `configs/` | Copia exacta de todos los ficheros de configuración usados |

> **¿Qué es la huella digital SHA-256?**
> Es como una firma matemática única del fichero. Si el fichero cambia aunque sea en un solo carácter, la huella cambia por completo. Así podemos saber con certeza si los datos de entrada eran exactamente los mismos en dos ejecuciones distintas.

### Cuando se genera una simulación

Al simular, se crea una carpeta con nombre `simulation_YYYYMMDD_HHMMSS` dentro de `outputs/simulations/`. Contiene:

| Archivo | Qué contiene |
|---|---|
| `sim_card.json` | Identificador de la simulación, **referencia al modelo padre que la generó**, y tamaño de muestra |
| `sim_config.json` | Configuración usada para esta simulación concreta |
| `sim.log` | Registro completo de la generación |
| `sanity_checks_report.csv` | Resultado de todas las comprobaciones de calidad |
| `synthetic_data/` | Los ficheros CSV con los datos sintéticos generados |

---

## MLflow: el panel de control (Híbrido)

Mientras que las carpetas `outputs/` guardan los ficheros reales, **MLflow es el cuadro de mando** que permite visualizar y comparar todo desde una interfaz web. 

**La herramienta detecta automáticamente dónde se está ejecutando:**

1.  **En AWS SageMaker**: Utiliza el servicio gestionado mediante una URI especial (ARN) y la librería `sagemaker-mlflow`. Los datos se comparten con todo el equipo en la nube.
2.  **En Local**: Si corres el código en tu ordenador, MLflow guarda los datos automáticamente en una carpeta local llamada `mlruns/`.

### ¿Qué información aparece en MLflow?

Cada ejecución aparece con:
- **Parámetros**: valores de configuración (épocas, tamaño de muestra, etc.).
- **Métricas**: resultados numéricos de calidad.
- **Etiquetas**: información extra como `run_status: SUCCESS` o `modelo_id`.
- **Artefactos**: copias de los ficheros más importantes disponibles para descarga.

---

## Cómo abrir el panel de MLflow

Dependiendo de dónde hayas ejecutado la herramienta, tienes dos formas de ver los resultados:

### Opción A: Si has ejecutado en AWS SageMaker Studio
El servidor está siempre activo en AWS.
1.  En el menú lateral de **SageMaker Studio**, ve a **MLflow** > **Tracking Servers**.
2.  Selecciona el servidor (ej. `app-WOVA56CVVLL2`) y pulsa **"Open MLflow UI"**.

### Opción B: Si has ejecutado en Local (Tu ordenador)
Debes lanzar tú mismo la interfaz desde la terminal:
1.  Activa el entorno: `source .venv_core/bin/activate`
2.  Lanza la UI: 
    ```bash
    mlflow ui --backend-store-uri ./mlruns --port 5001
    ```
3.  Abre en tu navegador: **http://127.0.0.1:5001**

---

## Cómo leer la interfaz de MLflow

Al abrir la URL verás algo así:

```
Experiments (barra izquierda)
├── SyntheticData-Training
│     run_name: modelo_20260226_113921   ← cada fila es un entrenamiento
│     run_status: SUCCESS
│     mostly.epochs: 100
│
└── SyntheticData-Simulation
      run_name: simulation_20260226_114500  ← cada fila es una simulación
      modelo_id: modelo_20260226_113921     ← qué modelo la generó
      sanity_failed_checks: 0
```

Haciendo clic en cualquier run puedes ver:
- Todos los parámetros con los que corrió
- Los artefactos descargables (configs, CSVs, logs)
