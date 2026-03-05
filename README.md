# Herramienta de Datos Sintéticos para el ENDS

<div style="display: flex; gap: 20px; align-items: center;">
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg/960px-Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg.png" alt="drawing" width="200"/>
        <img src="https://www.seguritecnia.es/wp-content/uploads/2024/07/ntt-data.jpg" alt="drawing" width="200"/>
        </div>

## Descripción
Esta herramienta está diseñada para facilitar la generación de datos sintéticos para el Espacio Nacional de Datos de Salud (ENDS).

## 1. Instalación

### 1.1 Clonar y acceder al repositorio

```bash
git clone https://umane.emeal.nttdata.com/git/analytics/projects/health/ends-pt/herramienta-datos-sinteticos.git
cd herramienta-datos-sinteticos
```

### 1.2 Setup Automático (Windows y Linux)

El script realiza automáticamente:
- Instalación de **uv**
- Instalación aislada de **Python 3.12.3**
- Creación de entornos:
  - `.venv_core`
  - `.venv_eval`

#### Linux / WSL

```bash
./scripts/setup.sh
```
si da errores de permiso revisar que tengas x haciendo ``ls -la``, puedes darle con:

```bash
chmod +x scripts/setup.sh
```

#### Windows (PowerShell)

```powershell
.\scripts\setup.ps1
```

---
## 2. Configuración

La herramienta utiliza varios archivos de configuración ubicados en el directorio `config/` que permiten personalizar el comportamiento del sistema de generación y evaluación de datos sintéticos.

> ⚠️ Lo único esencial a configurar es la ruta de los datos de entrada en `config/general_config.py`, llamada `DEFAULT_DATA_PATH`. El resto de configuraciones tienen valores por defecto que deberían funcionar sin tocarlos.

### 2.1 Configuración General (`config/general_config.py`)

Este archivo contiene la configuración principal del proyecto. Las variables más importantes son:

#### Rutas de Datos
```python
# Ruta por defecto de los datos de entrada
DEFAULT_DATA_PATH = "data/sintetico"

# Directorio raíz de las salidas
OUTPUTS_ROOT = "outputs"

# Directorios para resultados de entrenamiento y simulación
TRAINING_RESULTS_DIR = "outputs/training"
SIMULATION_RESULTS_DIR = "outputs/simulation"
```

Éstas son rutas relativas desde dentro del repositorio, la raíz del proyecto. La carpeta `data` no existe por defecto, tienes varias opciones:
- Crear la carpeta `data` y añadir tus datos ahí, referenciándola en `DEFAULT_DATA_PATH`.
- Crear la carpeta `data` y crear un link simbólico a otra carpeta donde tengas tus datos. Esta opción es útil si trabajas con datos grandes que no quieres copiar dentro del repositorio.

  - En Linux/WSL:
    ```bash
    ln -s /ruta/a/mis_datos data/sintetico
    ```

  - En Windows (PowerShell):
    ```powershell
    New-Item -ItemType Junction -Path ".\data\sintetico" -Target "C:\Users\...\datos"
    ```
- Modificar `DEFAULT_DATA_PATH` para apuntar a otra carpeta donde tengas tus datos directamente, usando una ruta absoluta:
```python
# Ejemplo de ruta absoluta
DEFAULT_DATA_PATH = '/home/obustosm/workspace/test/herramienta-datos-sinteticos/data/sintetico'
```

### 2.2 Configuración de Mostly AI (`config/mostly_ai_config.yaml`)

Este archivo define los parámetros del generador sintético de Mostly AI:

```yaml
generator:
  name: "generador_mostly_ai-"  # Prefijo del nombre del generador
  description: "Entrenamiento modular con Mostly AI"
  random_state: 1  # Semilla para reproducibilidad

model_settings:
  max_training_time: 3
  enable_model_report: False  # Generar reporte del modelo

  # Configuración de privacidad diferencial
  differential_privacy:
    max_epsilon: null  # Presupuesto de privacidad (null = sin límite)
    delta: 0.00001  # Parámetro delta de privacidad diferencial
    noise_multiplier: 1.5  # Multiplicador de ruido
    max_grad_norm: 1.0  # Norma máxima del gradiente
    value_protection_epsilon: 1.0  # Epsilon de protección de valores
```

### 2.3 Reglas Lógicas (`config/rules.yaml`)

Define reglas de consistencia que se aplicarán a los datos sintéticos generados. Esto asegura que los datos mantengan coherencia semántica y temporal.

```yaml
rules:
  # Regla de consistencia de fechas
  - type: "date_consistency"
    table_name: "procedure_occurrence"
    origin_col: "procedure_datetime"
    target_col: "procedure_end_datetime"
    aux_col: "procedure_duration_days"

  # Regla de consistencia de ranking semántico
  - type: "semantic_ranking_consistency"
    table_name: "test"
    origin_col: "disease"
    target_col: "medication"

  - type: "semantic_ranking_consistency"
    table_name: "test"
    origin_col: "ispediatric"
    target_col: "disease"
```

**Tipos de reglas disponibles:**

1. **date_consistency**: Asegura que las fechas de inicio sean anteriores a las de fin y que la duración sea correcta.
   - `origin_col`: Columna con la fecha de inicio
   - `target_col`: Columna con la fecha de fin
   - `aux_col`: Columna con la duración calculada

2. **semantic_ranking_consistency**: Mantiene la distribución proporcional entre categorías agrupadas.
   - `origin_col`: Columna de agrupación
   - `target_col`: Columna objetivo a validar

3. **semantic_proportional_consistency**: Similar al ranking pero enfocado en proporciones exactas.

Consulta [docs/REGLAS_LOGICAS.md](docs/REGLAS_LOGICAS.md) para más detalles sobre el funcionamiento de las reglas lógicas.


## 3. Ejecución

### 3.1 Maneras de ejecutar
#### Opción A: Scripts de Ayuda

**Linux**
```bash
./scripts/run.sh {comando}
```

**Windows**
```powershell
.\scripts\run.ps1 {comando}
```
Los comandos disponibles son: 'train', 'sim', 'eval'.

| Acción | Linux | Windows | Descripción |
|------|------|---------|-------------|
| Asistente | `./scripts/run.sh` | `.\scripts\run.ps1` | Te lleva al modo interactivo de train/sim directamente |
| Entrenar | `./scripts/run.sh train` | `.\scripts\run.ps1 train` | Entrenamiento |
| Simular | `./scripts/run.sh sim` | `.\scripts\run.ps1 sim` | Generación |
| Evaluar | `./scripts/run.sh eval` | `.\scripts\run.ps1 eval` | `src.eval` |

---

#### Opción B: Ejecución manual del pipeline de entrenamiento/simulación

##### Activar entorno Core

**Linux**
```bash
source .venv_core/bin/activate
```

**Windows**
```powershell
.venv_core\Scripts\activate
```

##### Ejecución

```bash
python -m src.main [argumentos]
```
##### Argumentos
- `--mode`
  - `train` → entrenar y simular
  - `simulation` → solo generar

- `--files`
  - Directorio: `data/mis_datos/`
  - Lista: `data/a.csv data/b.xlsx`

- `--sample-size`
  - Número de registros a generar
##### Ejemplos

Entrenar y simular 1000 filas:
```bash
python -m src.main --mode train --files ./data/mis_datos/ --sample-size 1000
```

Entrenar sin simular:
```bash
python -m src.main --mode train --files \
  data/sintetico/person.csv \
  data/sintetico/procedure_occurrence.csv
```


#### Opción C: Ejecución manual del pipeline de evaluación

Para ejecutar `src.eval`, activa el entorno:

```bash
.venv_eval
```

---

## 4. Tests en VSCode

La carpeta `tests/` contiene tests funcionales del pipeline. Puedes ejecutarlos directamente desde VSCode haciendo clic en el botón ▶️.

### Configuración inicial (solo la primera vez)

**Abre el proyecto en VSCode**:
   - La extensión de Python debe estar instalada y debes tener el venv_core activado en VSCode. Para esto, abre la paleta de comandos (Ctrl+Shift+P) y selecciona "Python: Select Interpreter". Elige el intérprete que corresponda a `.venv_core`.
   - VSCode detectará automáticamente los tests

### Ejecutar tests

1. Haz clic en el icono de **Testing** (🧪) en la barra lateral izquierda de VSCode
2. Verás los tests organizados por categorías:
   - `TestDataLoading` - Tests de carga de archivos (rápidos)
   - `TestPreprocessing` - Tests de preprocesamiento (rápidos)
   - `TestE2EPipeline` - Test completo del pipeline (lento, requiere Mostly AI)
3. Haz clic en ▶️ junto a cualquier test para ejecutarlo

## 🛠️ 5. Funcionalidades Principales

| Fase | Funcionalidad | Descripción |
|------|---------------|-------------|
| **Ingesta** | Ficheros (Multi-formato) | De momento solo carga archivos. Soporta carga de CSV, Excel (.xlsx) y Parquet |
| **Procesado** | Metadata + Preprocessing | Limpieza y preparación de datos muy básica, y extracción de metadatos (tipos de columnas, y relaciones entre tablas) |
| **Entrenamiento** | Mostly AI | Genera un modelo (generador) basado en los datos reales |
| **Simulación** | Generación | Permite crear desde unos pocos registros hasta millones de filas sintéticas |
| **Evaluación** |	Métricas |	Análisis de fidelidad y privacidad (requiere entorno de evaluación) |

---

## 6. Formatter y Linter (Opcional)

Para mantener el código limpio, organizado y libre de errores comunes, utilizamos **Ruff**. Ruff es una herramienta "todo en uno" para formatear, ordenador imports, ahcer linting...

### 6.1 Configuración del entorno de desarrollo
Una vez activado tu entorno virtual, instala las herramientas de desarrollo:

```bash
pip install ruff pre-commit
```

### 6.2 Activación de la Limpieza Automática (Pre-commit)
Hemos configurado "hooks" de pre-commit. Esto es como un "robot guardián" que revisa tu código justo antes de cada git commit. Si encuentra fallos de estilo o errores, los corregirá automáticamente y te avisará.

Para activar este guardián, ejecuta este comando una sola vez:

```Bash
pre-commit install
```

### 6.3 ¿Cómo trabajar con estas herramientas?
- Formateo automático: Si usas VS Code, instala la extensión Ruff. El código se ordenará solo cada vez que guardes el archivo (Ctrl+S).

- Al hacer un Commit: Cuando hagas git commit, verás que Ruff se ejecuta.

- Si todo está bien, el commit se creará.

   - Si Ruff hace cambios automáticos (como ordenar importaciones), el commit se detendrá. Simplemente añade esos cambios con git add . y vuelve a intentar el commit.

   - Revisión manual: Si quieres revisar todo el proyecto sin hacer un commit, usa:

   ```Bash
   pre-commit run --all-files
   ```

### 6.4 Documentación de Docstrings
Para mantener la documentación de nuestro código clara y consistente, seguimos el formato de docstrings siguiente:

```python
def mi_funcion(param1, param2):
    """Descripción breve de lo que hace la función. 

    Descripción más detallada si es necesario.

    Args:
        param1 (tipo): Descripción de param1.
        param2 (tipo): Descripción de param2.

    Returns:
        tipo: Descripción de lo que devuelve la función.
    Raises:
        TipoError: Descripción de la condición que causa este error.

    Example:
        >>> resultado = mi_funcion(valor1, valor2)
        >>> print(resultado)
         resultado esperado
    """
    pass
```