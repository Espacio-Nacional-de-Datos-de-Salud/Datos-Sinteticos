from typing import Any
from src.core.utils import ModelEncodingType


class MetadataValidator:
    """Valida y edita interactivamente metadatos de tablas relacionales.

    Presenta metadatos extraídos al usuario permitiendo confirmar o modificar
    tipos de codificación y relaciones (claves foráneas) antes de usar en síntesis.
    """

    def __init__(self, engine_name: str = "mostly") -> None:
        """Inicializa validador de metadatos para un motor específico.

        Args:
            engine_name (str): Nombre del motor ('mostly' u otro). Defaults to \"mostly\".
        """
        self.engine_name = engine_name

    def validate_relationships(self, data_dfs: dict, relationships: dict) -> dict:
        """Valida interactivamente las relaciones foráneas entre tablas.

        Muestra relaciones detectadas y permite al usuario añadir, eliminar o
        confirmar claves foráneas antes de continuar.

        Args:
            data_dfs (dict[str, pd.DataFrame]): Diccionario de DataFrames para validación.
            relationships (dict): Estructura con PKs y FKs
                {pks, fks: [{parent, child, fk_column, pk_column}, ...]}.

        Returns:
            dict: Relaciones validadas y potencialmente modificadas.

        Example:
            >>> validator = MetadataValidator()
            >>> rels = validator.validate_relationships(data_dict, relationships)
        """
        while True:
            self._print_relationships(relationships)
            print("\n[?] ¿Deseas modificar alguna relación (FK)?")
            if input("    (y) Sí / (Enter) No: ").strip().lower() != "y":
                break

            self._edit_relationships_flow(data_dfs, relationships)

        return relationships

    def validate_encoding_types(self, types_data: dict) -> dict:
        """Valida interactivamente tipos de codificación de columnas.

        Muestra tipos detectados y permite al usuario modificarlos antes de
        finalizar la configuración del motor de síntesis.

        Args:
            types_data (dict): Estructura de tipos
                {tabla: {columna: ModelEncodingType, ...}, ...}.

        Returns:
            dict: Tipos de codificación validados y potencialmente modificados.

        Example:
            >>> types = validator.validate_encoding_types(types_data)
            >>> print(types['users']['age'])  # ModelEncodingType.tabular_numeric_auto
        """
        while True:
            self._print_column_types(types_data)
            print("\n[?] ¿Deseas modificar algún tipo de dato?")
            if input("    (y) Sí / (Enter) No: ").strip().lower() != "y":
                break

            self._edit_types_flow(types_data)

        return types_data

    # --- UI Helpers ---
    def _print_column_types(self, types_data: dict) -> None:
        """Imprime tabla de tipos de codificación por columna.

        Args:
            types_data (dict): Estructura de tipos a mostrar.
        """
        print("\n" + "=" * 60)
        print(f"{'TABLA / COLUMNA':<35} | {'TIPO'}")
        print("=" * 60)

        for table_name, columns_dict in types_data.items():
            print(f"📂 {table_name}")

            # FIX: Iterate directly over the dictionary, as keys are columns and values are Enums
            for col_name, encoding_type in columns_dict.items():
                # FIX: 'encoding_type' is the Enum directly, not a dict
                t = str(encoding_type).split(".")[-1]
                print(f"   └─ {col_name:<30} | {t}")

    def _print_relationships(self, relationships: dict) -> None:
        """Imprime tabla de relaciones foráneas detectadas.

        Args:
            relationships (dict): Estructura con PKs y FKs a mostrar.
        """
        print("\n" + "=" * 60)
        print(f"{'TABLA HIJA . FOREIGN KEY':<35} | {'PADRE'}")
        print("=" * 60)

        fks_list = relationships.get("fks", [])

        if not fks_list:
            print("   [!] Sin relaciones.")
            return

        for fk in fks_list:
            child_str = f"{fk.get('child', '?')}.{fk.get('fk_column', '?')}"
            parent_str = fk.get("parent", "?")
            print(f"   {child_str:<35} -> {parent_str}")

    def _let_user_pick(self, options: list, label_fn) -> Any:
        """Solicita al usuario que seleccione una opción de una lista.

        Args:
            options (list): Lista de opciones disponibles.
            label_fn: Función para extraer etiqueta de cada opción.

        Returns:
            Any: Opción seleccionada o None si cancela.
        """
        if not options:
            return None
        for i, opt in enumerate(options):
            print(f"   [{i}] {label_fn(opt)}")
        print("   [x] Cancelar")
        try:
            sel = input("   >> ").strip()
            if sel == "x":
                return None
            return options[int(sel)]
        except (ValueError, IndexError):
            return None

    def _edit_types_flow(self, types_data: dict) -> None:
        # 1. Pick Table
        table_name = self._let_user_pick(list(types_data.keys()), lambda x: x)
        if not table_name:
            return

        # FIX: The value of types_data[table_name] IS the dictionary of columns
        columns_dict = types_data[table_name]

        # 2. Pick Column
        col_name = self._let_user_pick(list(columns_dict.keys()), lambda x: x)
        if not col_name:
            return

        # 3. Pick Type
        types = [x.name for x in ModelEncodingType]
        tn = self._let_user_pick(types, lambda x: x)

        if tn:
            # FIX: Assign the new Enum directly to the column key
            columns_dict[col_name] = getattr(ModelEncodingType, tn)
            print(f"✅ Cambio aplicado: {col_name} -> {tn}")

    def _edit_relationships_flow(self, data_dfs: dict, relationships: dict):
        if "fks" not in relationships:
            relationships["fks"] = []

        fks_list = relationships["fks"]

        # 1. Select Child Table (Use data_dfs keys because relationships keys are just 'pks'/'fks')
        print("\nSelecciona la tabla HIJA:")
        table_name = self._let_user_pick(list(data_dfs.keys()), lambda x: x)
        if not table_name:
            return

        # 2. Action
        action = self._let_user_pick(["Añadir FK", "Eliminar FK"], lambda x: x)
        if not action:
            return

        # --- DELETE LOGIC ---
        if action == "Eliminar FK":
            # Filter FKs that belong to the selected table (child)
            current_table_fks = [x for x in fks_list if x.get("child") == table_name]

            if not current_table_fks:
                print("   [!] No hay FKs para borrar en esta tabla.")
                return

            # Let user pick which specific FK to delete
            fk_to_del = self._let_user_pick(
                current_table_fks, lambda x: f"{x.get('fk_column')} -> {x.get('parent')}"
            )

            if fk_to_del:
                fks_list.remove(fk_to_del)
                print("🗑️ Relación eliminada.")

        # --- ADD LOGIC ---
        elif action == "Añadir FK":
            # Pick Column from Child Table
            columns = data_dfs[table_name].columns.tolist()
            print(f"\nSelecciona la columna FK en {table_name}:")
            col_name = self._let_user_pick(columns, lambda x: x)
            if not col_name:
                return

            # Pick Parent Table
            other_tables = [t for t in data_dfs.keys() if t != table_name]
            print("\nSelecciona la tabla PADRE:")
            parent_name = self._let_user_pick(other_tables, lambda x: x)
            if not parent_name:
                return

            # Attempt to find PK of parent automatically from 'pks' dictionary
            # Fallback to 'id' or ask user if necessary (simplified here to auto-lookup)
            parent_pk = relationships.get("pks", {}).get(parent_name, f"{parent_name}_id")

            # Construct new FK dictionary matching your structure
            new_fk = {
                "parent": parent_name,
                "child": table_name,
                "fk_column": col_name,
                "pk_column": parent_pk,
            }

            fks_list.append(new_fk)
            print(f"✅ Relación añadida: {table_name}.{col_name} -> {parent_name}.{parent_pk}")

    def _sanity_check(self, parent_df, pk_col, child_df, fk_col) -> tuple[bool, str]:
        """Valida integridad de relación foránea potencial.

        Verifica compatibilidad de tipos y presencia de huérfanos.

        Args:
            parent_df (pd.DataFrame): DataFrame tabla padre.
            pk_col (str): Nombre columna PK en tabla padre.
            child_df (pd.DataFrame): DataFrame tabla hija.
            fk_col (str): Nombre columna FK en tabla hija.

        Returns:
            tuple[bool, str]: (es_válida, descripción). True si pasa validación.
        """
        # Type check
        if parent_df[pk_col].dtype.kind != child_df[fk_col].dtype.kind:
            return (
                False,
                f"Tipos incompatibles ({parent_df[pk_col].dtype} vs {child_df[fk_col].dtype})",
            )

        # Orphan check
        child_vals = child_df[fk_col].dropna().unique()
        parent_vals = set(parent_df[pk_col].dropna().unique())

        if len(child_vals) == 0:
            return False, "Columna hija vacía"

        orphans = [v for v in child_vals if v not in parent_vals]
        orphan_rate = len(orphans) / len(child_vals)

        if orphan_rate > 0.1:
            return False, f"Demasiados huérfanos ({orphan_rate:.1%})"

        return True, "OK"
