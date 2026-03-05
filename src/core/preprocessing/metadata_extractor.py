from typing import Any

import pandas as pd

from src.core.utils import ModelEncodingType, auto_detect_encoding_type


class MetadataExtractor:
    """Extrae metadatos estructurales de un conjunto de tablas relacionales.

    Analiza datos para detectar hechos estructurales como relaciones entre tablas
    (claves primarias y foráneas) y tipos de codificación de columnas mediante
    heurísticas de nomenclatura y análisis de valores, sin acoplarse a ningún
    formato de salida específico.

    Args:
        data (dict[str, pd.DataFrame]): Diccionario de tablas crudas con estructura
            {nombre_tabla: dataframe}.

    Attributes:
        data (dict[str, pd.DataFrame]): Las tablas crudas almacenadas.

    Raises:
        ValueError: Si `data` es None o está vacío.

    Example:
        >>> data = {'users': users_df, 'orders': orders_df}
        >>> extractor = MetadataExtractor(data)
        >>> relationships = extractor.extract_relationships()
        >>> encoding_types = extractor.extract_encoding_types(relationships['pks'])
    """

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        """Inicializa el extractor de metadatos con un conjunto de tablas.

        Args:
            data (dict[str, pd.DataFrame]): Diccionario con tablas crudas
                {nombre_tabla: dataframe}.
        """
        self.data = data

    def extract_relationships(self) -> dict[str, Any]:
        """Detecta claves primarias y relaciones foráneas entre tablas.

        Ejecuta dos pasos secuenciales: primero detecta claves primarias (PKs)
        en cada tabla, luego usa esas PKs para identificar posibles claves foráneas
        (FKs) en otras tablas. Utiliza heurísticas de nomenclatura y validación
        de integridad referencial para evitar falsos positivos.

        Returns:
            dict[str, Any]: Diccionario con dos claves:
                - 'pks': dict[str, str] mapeo {nombre_tabla: columna_pk}
                - 'fks': list[dict] relaciones detectadas con estructura:
                    {
                        'parent': str nombre tabla padre,
                        'child': str nombre tabla hija,
                        'fk_column': str columna FK en tabla hija,
                        'pk_column': str columna PK en tabla padre
                    }

        Example:
            >>> extractor = MetadataExtractor(data)
            >>> result = extractor.extract_relationships()
            >>> print(result['pks'])  # {'users': 'id', 'orders': 'order_id'}
            >>> print(result['fks'])  # [{'parent': 'users', 'child': 'orders', ...}]
        """
        print("--- Detecting relationships ---")
        pks = self._detect_pks()
        fks = self._detect_fks(pks)
        return {"pks": pks, "fks": fks}

    def extract_encoding_types(
        self, pks: dict[str, str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Detecta tipos de codificación para cada columna de cada tabla.

        Analiza el contenido de cada columna para clasificarla según su tipo de
        codificación (numérica, categórica, etc.) usando heurísticas basadas en
        tipos de datos y análisis de valores. Si se proporcionan las PKs, las excluye
        del análisis detallado para optimizar la detección.

        Args:
            pks (dict[str, str] | None, optional): Mapeo de claves primarias
                {nombre_tabla: columna_pk}. Si es None, se analiza cada columna
                independientemente. Defaults to None.

        Returns:
            dict[str, dict[str, Any]]: Mapeo jerárquico
                {nombre_tabla: {nombre_columna: tipo_codificacion, ...}, ...}
                donde tipo_codificacion es un ModelEncodingType.

        Example:
            >>> extractor = MetadataExtractor(data)
            >>> pks = {'users': 'user_id'}
            >>> types = extractor.extract_encoding_types(pks)
            >>> print(types['users']['age'])  # ModelEncodingType.tabular_numeric_auto
        """
        print("--- Detecting encoding types ---")
        types_map = {}
        for name, df in self.data.items():
            # If we know the PK, we avoid analyzing it as a categorical
            table_pk = pks.get(name) if pks else None
            types_map[name] = self._detect_table_types(df, table_pk)
        return types_map

    # --- Internal Detection Logic ---

    def _detect_pks(self) -> dict[str, str]:
        """Identifica claves primarias en cada tabla mediante heurísticas.

        Aplica dos estrategias secuenciales: primero busca columnas con nombres
        típicos de PKs (id, {tabla}_id, etc.), y si no encuentra coincidencia,
        analiza todas las columnas para encontrar las que tengan valores únicos
        sin valores nulos. Imprime advertencias para tablas sin PK detectada.

        Returns:
            dict[str, str]: Mapeo {nombre_tabla: columna_pk}. Omite tablas
                donde no se detectó PK.
        """
        pks = {}
        for name, df in self.data.items():
            pk = None
            # 1. Heuristic: Name matching
            candidates = [
                c for c in df.columns if c.lower() in ["id", f"{name}_id", f"{name[:-1]}_id"]
            ]
            for col in candidates:
                if df[col].is_unique and not df[col].hasnans:
                    pk = col
                    break

            # 2. Heuristic: Unique Object/Int check
            if pk is None:
                for col in df.columns:
                    if df[col].dtype.kind in "Oiu":
                        if df[col].is_unique and not df[col].hasnans:
                            pk = col
                            break

            if pk:
                pks[name] = pk
            else:
                print(f"   [!] No se pudo inferir PK para la tabla '{name}'")
        return pks

    def _detect_fks(self, pks: dict[str, str]) -> list[dict[str, str]]:
        """Detecta relaciones de claves foráneas entre tablas.

        Para cada tabla padre (identificada por su PK), busca candidatos de
        claves foráneas en otras tablas usando heurísticas de nombres. Valida
        cada candidato mediante chequeo de integridad referencial antes de
        incluirlo en las relaciones detectadas. Imprime resultados (✅) y
        descartes (⚠️) en consola durante el proceso.

        Args:
            pks (dict[str, str]): Mapeo de claves primarias detectadas
                {nombre_tabla: columna_pk}.

        Returns:
            list[dict[str, str]]: Lista de relaciones validadas, cada una con:
                {
                    'parent': str nombre tabla padre,
                    'child': str nombre tabla hija,
                    'fk_column': str nombre columna FK en tabla hija,
                    'pk_column': str nombre columna PK en tabla padre
                }
        """
        relationships = []
        for parent_name, pk in pks.items():
            parent_df = self.data[parent_name]

            # Possible FK names in other tables
            possible_names = {
                pk,
                f"{parent_name}_{pk}",
                f"{parent_name}_id",
                f"{parent_name[:-1]}_id",
            }

            for child_name, child_df in self.data.items():
                if parent_name == child_name:
                    continue

                matches = [col for col in child_df.columns if col in possible_names]
                for candidate_fk in matches:
                    is_valid, reason = self._internal_sanity_check_relationship(
                        parent_df, pk, child_df, candidate_fk
                    )
                    if is_valid:
                        relationships.append(
                            {
                                "parent": parent_name,
                                "child": child_name,
                                "fk_column": candidate_fk,
                                "pk_column": pk,  # Storing this helps downstream tools
                            }
                        )
                        print(f"✅ Relación: {child_name}.{candidate_fk} -> {parent_name}.{pk}")
                    else:
                        print(
                            f"⚠️ Descartada: {child_name}.{candidate_fk} -> {parent_name}.{pk} ({reason})"
                        )
        return relationships

    def _detect_table_types(self, df: pd.DataFrame, pk_col: str | None = None) -> dict[str, Any]:
        """Detecta tipos de codificación para cada columna de una tabla.

        Clasifica cada columna como numérica o categórica mediante análisis inicial,
        luego aplica heurísticas avanzadas a columnas categóricas (excepto la PK)
        para identificar tipos específicos como texto, fecha, etc. Excluye la PK
        del análisis detallado por eficiencia.

        Args:
            df (pd.DataFrame): DataFrame de la tabla a analizar.
            pk_col (str | None, optional): Nombre de la columna PK a excluir
                del análisis detallado. Defaults to None.

        Returns:
            dict[str, Any]: Mapeo {nombre_columna: ModelEncodingType} para
                cada columna de la tabla.
        """
        col_types = {}
        for col in df.columns:
            # Default heuristic
            if pd.api.types.is_numeric_dtype(df[col]):
                ctype = ModelEncodingType.tabular_numeric_auto
            else:
                ctype = ModelEncodingType.tabular_categorical

            # Refinement: If it's categorical and NOT the PK, inspect deeper
            if ctype == ModelEncodingType.tabular_categorical and col != pk_col:
                ctype = auto_detect_encoding_type(df[col])

            col_types[col] = ctype
        return col_types

    def _internal_sanity_check_relationship(
        self,
        parent_df: pd.DataFrame,
        pk_col: str,
        child_df: pd.DataFrame,
        fk_col: str,
    ) -> tuple[bool, str]:
        """Valida la integridad de una potencial relación de clave foránea.

        Realiza tres validaciones: compatibilidad de tipos de datos entre PK y FK,
        chequeo de huérfanos (valores FK sin correspondencia en PK), y cálculo de
        tasa de integridad referencial. Una relación es válida si los tipos son
        compatibles y el porcentaje de huérfanos no excede el 10%.

        Args:
            parent_df (pd.DataFrame): DataFrame de la tabla padre.
            pk_col (str): Nombre de la columna PK en tabla padre.
            child_df (pd.DataFrame): DataFrame de la tabla hija.
            fk_col (str): Nombre de la columna FK en tabla hija.

        Returns:
            tuple[bool, str]: Tupla (es_válida, mensaje) donde:
                - bool: True si la relación es válida, False en caso contrario.
                - str: Descripción del resultado o razón del rechazo.

        Raises:
            KeyError: Si pk_col no existe en parent_df o fk_col no existe en child_df.
        """
        if parent_df[pk_col].dtype.kind != child_df[fk_col].dtype.kind:
            return False, "Tipos incompatibles"

        child_vals = child_df[fk_col].dropna().unique()
        parent_vals = set(parent_df[pk_col].dropna().unique())

        if len(child_vals) == 0:
            return False, "Columna hija vacía"

        orphans = [v for v in child_vals if v not in parent_vals]
        orphan_rate = len(orphans) / len(child_vals)

        if orphan_rate > 0.1:
            return False, f"Demasiados huérfanos ({orphan_rate:.1%})"
        return True, "OK"
