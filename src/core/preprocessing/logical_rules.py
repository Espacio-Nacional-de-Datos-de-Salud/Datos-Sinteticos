"""
Sistema de Reglas Lógicas para Generación de Datos Sintéticos.

Este módulo implementa un patrón de diseño en tres fases para garantizar la coherencia
de los datos generados por modelos de IA (que suelen fallar en lógica determinista):

1. PRE: Transformación de datos complejos a representaciones simplificadas (numéricas/continuas)
   antes del entrenamiento. Se eliminan las columnas objetivo.
2. POST: Reconstrucción determinista de las columnas objetivo a partir de las predicciones
   del modelo sobre las variables auxiliares.
3. SANITY: Validación final para asegurar que se cumplen las reglas de negocio.
"""

import bisect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.core.errors import RelationshipNotDefinedError


@dataclass
class LogicalRule(ABC):
    """
    Clase base abstracta para definir una regla lógica de negocio.

    Args:
        table_origin (str): (Opcional) Nombre de la tabla origen de datos (contexto/referencia).
        table_target (str): Nombre de la tabla sobre la que aplica la regla (donde está el target).
    """

    table_origin: str = None
    table_target: str = None
    sanity_only: bool = False

    @abstractmethod
    def apply_pre(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transforma los datos originales en un formato optimizado para el modelo.
        Suele crear columnas auxiliares y eliminar las columnas objetivo (target).

        Args:
            df (pd.DataFrame): DataFrame original (puede incluir columnas de table_origin tras el join
            que hace el Manager).

        Returns:
            pd.DataFrame: DataFrame transformado.
        """
        pass

    @abstractmethod
    def apply_post(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Reconstruye las columnas objetivo basándose en las predicciones del modelo.

        Args:
            df (pd.DataFrame): DataFrame con datos sintéticos (incluye auxiliares).

        Returns:
            pd.DataFrame: DataFrame final con la lógica de negocio aplicada.
        """
        pass

    @abstractmethod
    def sanity_check(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Verifica que los datos finales cumplan la regla estricta.

        Args:
            df (pd.DataFrame): DataFrame sintético final.

        Returns:
            pd.DataFrame: Subconjunto de filas que NO cumplen la regla (vacío si todo OK).
        """
        pass


@dataclass
class LogicalRuleManager:
    """
    Orquestador que gestiona la colección de reglas y su ejecución secuencial.

    Mantiene el estado de las reglas necesarias para la reconstrucción.

    Se rellenan los argumentos a través del método add_rule() (arg 'rule') y de
    los argumentos del método apply_all_pre() (arg 'relationships').

    Args:
        rules (List[LogicalRule]): Lista de reglas registradas.
        relationships (Dict): Diccionario de metadatos PK/FK.
                              Formato: {('tabla_hija', 'tabla_padre'): ('fk_col', 'pk_col')}

    Returns:
        LogicalRuleManager: Instancia de la dataclass.
    """

    rules: list[LogicalRule] = field(default_factory=list)
    relationships: dict[tuple[str, str], tuple[str, str]] | None = field(default=None)

    def add_rule(self, rule: LogicalRule) -> None:
        """Registra una nueva regla en el gestor.

        Args:
            rule (LogicalRule): Instancia de la regla a agregar.
        """
        self.rules.append(rule)

    def _get_joined_view(
        self, rule: LogicalRule, data_dict: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """Crea una vista temporal con datos de la tabla de referencia si es necesario."""
        main_df = data_dict[rule.table_target]

        if not rule.table_origin or rule.table_origin == rule.table_target:
            return main_df.copy()

        key = (rule.table_target, rule.table_origin)
        reverse_key = (rule.table_origin, rule.table_target)

        join_config = self.relationships.get(key) or self.relationships.get(reverse_key)

        if not join_config:
            raise RelationshipNotDefinedError(
                f"No relationship defined between '{rule.table_target}' and '{rule.table_origin}'"
            )

        origin_df = data_dict[rule.table_origin]
        left_col, right_col = join_config

        if key in self.relationships:
            merged = pd.merge(
                main_df,
                origin_df,
                left_on=left_col,
                right_on=right_col,
                how="left",
                suffixes=("", "_origin"),
            )
        else:
            merged = pd.merge(
                main_df,
                origin_df,
                left_on=right_col,
                right_on=left_col,
                how="left",
                suffixes=("", "_origin"),
            )

        return merged

    def _strip_origin_columns(
        self, joined_df: pd.DataFrame, rule: LogicalRule, data_dict: dict
    ) -> pd.DataFrame:
        """
        Mantiene las columnas originales de la tabla target y las nuevas auxiliares,
        eliminando solo las que se trajeron del join de la tabla origen.
        """
        if (
            not rule.table_origin
            or rule.table_origin not in data_dict
            or rule.table_origin == rule.table_target
        ):
            return joined_df

        origin_columns = set(data_dict[rule.table_origin].columns)

        key = (rule.table_target, rule.table_origin)
        reverse_key = (rule.table_origin, rule.table_target)
        join_config = self.relationships.get(key) or self.relationships.get(reverse_key)

        fk_to_preserve = join_config[0] if key in self.relationships else join_config[1]

        cols_to_keep = [
            c for c in joined_df.columns if ((c not in origin_columns) or (c == fk_to_preserve))
        ]

        return joined_df[cols_to_keep]

    def apply_all_pre(
        self,
        data_dict: dict[str, pd.DataFrame],
        relationships: dict[tuple[str, str], tuple[str, str]],
    ) -> dict[str, pd.DataFrame]:
        """
        Ejecuta la fase de preprocesado de todas las reglas registradas.

        Args:
            data_dict (Dict[str, pd.DataFrame]): Diccionario {nombre_tabla: dataframe}.
            relationships (Dict): Diccionario de metadatos PK/FK.
                                  Formato: {('tabla_hija', 'tabla_padre'): ('fk_col', 'pk_col')}

        Returns:
            Dict[str, pd.DataFrame]: Diccionario de datos transformados.
        """
        self.relationships = relationships

        processed_data = data_dict.copy()
        for rule in self.rules:
            if rule.table_target in processed_data:
                print(
                    f"Applying PRE rule: {type(rule).__name__} on {rule.table_target} (Origin: {rule.table_origin})"
                )

                view_df = self._get_joined_view(rule, processed_data)

                # Siempre ejecutamos apply_pre para que la regla aprenda metadatos (state)
                transformed_view = rule.apply_pre(view_df)

                if rule.sanity_only:
                    print(
                        "ℹ️ Sanity-only mode: Discarding data transformations, keeping internal state."
                    )
                    continue

                processed_data[rule.table_target] = self._strip_origin_columns(
                    transformed_view, rule, processed_data
                )

            else:
                print(f"⚠️ Skipped PRE: Table '{rule.table_target}' not found.")
        return processed_data

    def apply_all_post(self, data_dict: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """
        Ejecuta la fase de reconstrucción.
        IMPORTANTE: Se ejecuta en orden inverso (LIFO) para manejar dependencias entre reglas.

        Args:
            data_dict (Dict[str, pd.DataFrame]): Datos sintéticos brutos.

        Returns:
            Dict[str, pd.DataFrame]: Datos sintéticos reconstruidos.
        """
        processed_data = data_dict.copy()
        for rule in reversed(self.rules):
            if rule.table_target in processed_data:
                if rule.sanity_only:
                    print("⚠️ Skipped POST: Running in mode sanity-only.")
                    continue
                print(f"Applying POST rule: {type(rule).__name__} on {rule.table_target}")

                # 1. Crear vista (join si hace falta para reconstruir)
                view_df = self._get_joined_view(rule, processed_data)

                # 2. Aplicar regla
                reconstructed_view = rule.apply_post(view_df)

                # 3. Limpiar y guardar
                processed_data[rule.table_target] = self._strip_origin_columns(
                    reconstructed_view, rule, processed_data
                )

            else:
                print(f"⚠️ Skipped POST: Table '{rule.table_target}' not found.")
        return processed_data

    def run_all_sanity_checks(self, data_dict: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Ejecuta las validaciones de todas las reglas y retorna un reporte desglosado.

        Cada regla produce exactamente una fila en el reporte con su resultado
        individual (PASS, FAIL o SKIPPED).

        Args:
            data_dict (Dict[str, pd.DataFrame]): Datos finales a validar.

        Returns:
            pd.DataFrame: Reporte con columnas [check, rule, table, status,
                failed_rows, total_rows, details].
        """
        rows: list[dict] = []

        print("\n--- EJECUCIÓN DE SANITY CHECKS ---")

        for rule in self.rules:
            rule_name = type(rule).__name__

            if rule.table_target not in data_dict:
                print(f"SKIPPED | {rule_name} (Table '{rule.table_target}' not found)")
                rows.append(
                    {
                        "check": rule_name,
                        "rule": rule_name,
                        "table": rule.table_target,
                        "status": "SKIPPED",
                        "failed_rows": 0,
                        "total_rows": 0,
                        "details": f"Table '{rule.table_target}' not found in data",
                    }
                )
                continue

            view_df = self._get_joined_view(rule, data_dict)
            total = len(view_df)
            errors = rule.sanity_check(view_df)
            n_errors = len(errors)

            if n_errors == 0:
                print(f"✅ PASSED | {rule_name} on '{rule.table_target}'")
                rows.append(
                    {
                        "check": rule_name,
                        "rule": rule_name,
                        "table": rule.table_target,
                        "status": "PASS",
                        "failed_rows": 0,
                        "total_rows": total,
                        "details": "",
                    }
                )
            else:
                print(f"❌ FAILED | {rule_name} on '{rule.table_target}' ({n_errors} errors)")
                rows.append(
                    {
                        "check": rule_name,
                        "rule": rule_name,
                        "table": rule.table_target,
                        "status": "FAIL",
                        "failed_rows": n_errors,
                        "total_rows": total,
                        "details": f"{n_errors}/{total} rows failed",
                    }
                )

        if not rows:
            print("No hay reglas registradas.")
            return pd.DataFrame()

        report = pd.DataFrame(rows)
        passed = (report["status"] == "PASS").sum()
        total_checks = len(report)
        print(f"\nResultado: {passed}/{total_checks} checks pasados.")
        return report


@dataclass
class DateConsistencyRule(LogicalRule):
    """
    Garantiza la coherencia temporal entre dos fechas (inicio y fin).
    Transforma la fecha fin en una 'duración' (días) para que el modelo la aprenda más fácilmente.

    Args:
        origin_col (str): Nombre columna fecha inicio (Origen).
        target_col (str): Nombre columna fecha fin (Objetivo - será eliminada en PRE).
        aux_col (str, optional): Nombre para la columna auxiliar. Default: auto-generado.
    """

    origin_col: str = None
    target_col: str = None
    aux_col: str = None
    table_origin: str = None
    table_target: str = None

    def __post_init__(self):
        aux_suffix = "duration"
        if self.aux_col is None:
            self.aux_col = f"{aux_suffix}_{self.target_col}"

    def apply_pre(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df[self.origin_col] = pd.to_datetime(df[self.origin_col])
        df[self.target_col] = pd.to_datetime(df[self.target_col])

        # Cálculo de auxiliar y eliminación de target
        df[self.aux_col] = (df[self.target_col] - df[self.origin_col]).dt.days
        return df.drop(columns=[self.target_col])

    def apply_post(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df[self.origin_col] = pd.to_datetime(df[self.origin_col])

        # Reconstrucción determinista: Inicio + Duración simulada = Fin
        df[self.target_col] = df[self.origin_col] + pd.to_timedelta(df[self.aux_col], unit="D")
        return df.drop(columns=[self.aux_col])

    def sanity_check(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.origin_col not in df.columns or self.target_col not in df.columns:
            return pd.DataFrame()

        start_dates = pd.to_datetime(df[self.origin_col], errors="coerce")
        end_dates = pd.to_datetime(df[self.target_col], errors="coerce")

        inconsistent_mask = start_dates > end_dates
        failing_rows = df[inconsistent_mask].copy()

        if not failing_rows.empty:
            failing_rows["error_type"] = "TEMPORAL_INCONSISTENCY"
            failing_rows["table_origin"] = self.table_target
            failing_rows["details"] = (
                f"{self.origin_col} ("
                + failing_rows[self.origin_col].astype(str)
                + ") > "
                + f"{self.target_col} ("
                + failing_rows[self.target_col].astype(str)
                + ")"
            )
        return failing_rows


@dataclass
class SemanticConsistencyRule(LogicalRule, ABC):
    """
    Clase base para consistencia semántica en variables categóricas condicionadas.
    Convierte categorías en intervalos continuos [0,1] dentro de grupos específicos.

    Args:
        origin_col (str): Columna que agrupa.
        target_col (str): Columna categórica a transformar.
        aux_col (str, optional): Columna auxiliar numérica.
    """

    origin_col: str = None
    target_col: str = None
    aux_col: str = None
    table_origin: str = None
    table_target: str = None
    _mappings: dict[Any, list[tuple[float, Any]]] = field(default_factory=dict, init=False)
    _valid_combinations: dict[Any, set[Any]] = field(default_factory=dict, init=False)

    def __post_init__(self):
        aux_suffix = "score"
        if self.aux_col is None:
            self.aux_col = f"{self.target_col}_{aux_suffix}"

    @abstractmethod
    def _calculate_intervals(self, subset: pd.Series) -> list[tuple[float, Any]]:
        """
        Define cómo se distribuyen los intervalos en el rango [0,1] para un grupo.

        Args:
            subset (pd.Series): Serie con los valores categóricos del grupo actual.

        Returns:
            List[Tuple[float, Any]]: Lista de tuplas (limite_superior, nombre_categoria).
        """
        pass

    def apply_pre(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        unique_groups = df[self.origin_col].unique()

        # Columnas temporales para vectorización
        df["_temp_lower"] = 0.0
        df["_temp_upper"] = 0.0

        for group in unique_groups:
            mask = df[self.origin_col] == group
            subset = df[mask]

            if subset.empty:
                continue

            # Registramos las combinaciones válidas para el sanity check
            present_categories = set(subset[self.target_col].dropna().unique())
            self._valid_combinations[group] = present_categories

            # Delegamos el cálculo de intervalos a la implementación concreta
            group_intervals = self._calculate_intervals(subset[self.target_col])
            self._mappings[group] = group_intervals

            # Mapeo rápido categoría -> límites
            category_to_limits = {}
            prev_limit = 0.0
            for upper, category in group_intervals:
                category_to_limits[category] = (prev_limit, upper)
                prev_limit = upper
            for category, (lower, upper) in category_to_limits.items():
                cat_mask = mask & (df[self.target_col] == category)
                df.loc[cat_mask, "_temp_lower"] = lower
                df.loc[cat_mask, "_temp_upper"] = upper

        # Jittering: Generamos valor continuo dentro del intervalo asignado
        df[self.aux_col] = np.random.uniform(df["_temp_lower"], df["_temp_upper"])

        return df.drop(columns=[self.target_col, "_temp_lower", "_temp_upper"])

    def apply_post(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        def get_category(row):
            group = row[self.origin_col]
            aux_value = row[self.aux_col]

            if pd.isna(group) or pd.isna(aux_value):
                return None
            if group not in self._mappings:
                return None

            intervals = self._mappings[group]
            breakpoints = [i[0] for i in intervals]

            # Búsqueda binaria eficiente para encontrar en qué intervalo cae el score
            idx = bisect.bisect_left(breakpoints, aux_value)
            if idx >= len(intervals):
                idx = len(intervals) - 1

            return intervals[idx][1]

        df[self.target_col] = df.apply(get_category, axis=1)
        return df.drop(columns=[self.aux_col])

    def sanity_check(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Verifica que no existan combinaciones de (origin_col, target_col)
        que no estuvieran presentes en los datos originales.
        """
        if self.origin_col not in df.columns or self.target_col not in df.columns:
            return pd.DataFrame()

        # Si no se ejecutó apply_pre o no hay reglas guardadas, no podemos validar
        if not self._valid_combinations:
            return pd.DataFrame()

        error_mask = pd.Series(False, index=df.index)

        # Iteramos sobre los grupos CONOCIDOS para verificar sus reglas
        # Aquellos grupos que nunca vimos en PRE se ignoran (no tenemos regla para ellos)
        for group, allowed_cats in self._valid_combinations.items():
            # Filtramos filas que pertenecen al grupo actual
            # Nota: Manejo de NaN en origin_col si fuera necesario
            group_mask = df[self.origin_col] == group

            if not group_mask.any():
                continue

            # Verificamos si hay alguna categoría NO permitida para este grupo
            # Usamos ~isin(allowed_cats)
            # Nota: Si target_col es NaN, isin devuelve False, así que ~False=True (error).
            #       Si permitimos NaN en target, debería estar en allowed_cats.
            current_errors = group_mask & (~df[self.target_col].isin(allowed_cats))
            error_mask |= current_errors

        failing_rows = df[error_mask].copy()

        if not failing_rows.empty:
            failing_rows["error_type"] = "SEMANTIC_INCONSISTENCY"
            failing_rows["table_origin"] = self.table_target
            failing_rows["details"] = (
                f"Grupo '{self.origin_col}'="
                + failing_rows[self.origin_col].astype(str)
                + " tiene categoría inválida '{self.target_col}'="
                + failing_rows[self.target_col].astype(str)
            )

        return failing_rows


@dataclass
class SemanticProportionalConsistencyRule(SemanticConsistencyRule):
    """
    Estrategia Semántica PROPORCIONAL: El tamaño del intervalo es igual a la frecuencia real.
    Fuerza a que los datos sintéticos mantengan la distribución estadística original.

    Example:
        Si 'Gripe' aparece el 80% de las veces, su intervalo será de tamaño 0.8.
    """

    def _calculate_intervals(self, subset: pd.Series) -> list[tuple[float, Any]]:
        counts = subset.value_counts(normalize=True).sort_index()
        cumulative = 0.0
        intervals = []

        for category, freq in counts.items():
            upper = cumulative + freq
            intervals.append((upper, category))
            cumulative = upper

        if intervals:
            intervals[-1] = (1.0, intervals[-1][1])  # Corrección flotante
        return intervals


@dataclass
class SemanticRankingConsistencyRule(SemanticConsistencyRule):
    """
    Estrategia Semántica RANKING: Todos los intervalos tienen el mismo tamaño (equidistantes).
    Permite al modelo ajustar las proporciones (aprendiendo qué rangos de score prefiere),
    pero garantiza que solo se generen combinaciones semánticamente válidas.

    Example:
        Si hay 4 enfermedades, cada una tiene un intervalo de 0.25, ordenadas por frecuencia.
    """

    def _calculate_intervals(self, subset: pd.Series) -> list[tuple[float, Any]]:
        # Ordenamos por frecuencia para agrupar categorías comunes en scores bajos
        unique_categories = subset.value_counts().index.tolist()
        n = len(unique_categories)

        if n == 0:
            return []

        step = 1.0 / n
        cumulative = 0.0
        intervals = []

        for category in unique_categories:
            upper = cumulative + step
            intervals.append((upper, category))
            cumulative = upper

        if intervals:
            intervals[-1] = (1.0, intervals[-1][1])
        return intervals
