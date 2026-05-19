import polars as pl

from db.entities import Einheiten, Marktakteur, Type

_TYPE_TO_POLARS: dict[Type, type[pl.DataType]] = {
    Type.TEXT: pl.String,
    Type.INT: pl.Int64,
    Type.TIMESTAMP: pl.Datetime,
    Type.DATE: pl.Date,
    Type.BOOLEAN: pl.Boolean,
    Type.NUMERIC: pl.Float64,
}


def _column_dtype(column) -> type[pl.DataType]:
    col_opts = column.value
    sql_type: Type = col_opts[1]
    udf = col_opts[4] if len(col_opts) > 4 else None
    if udf is not None:
        return pl.String
    return _TYPE_TO_POLARS[sql_type]


def build_polars_schema(main_entity: Einheiten) -> dict[str, type[pl.DataType]]:
    # Column order must mirror MastrExporter.__create_select_stmts:
    # main entity columns, followed by Marktakteur columns.
    # Marktakteur columns are prefixed to disambiguate from main-entity columns
    # that share a name (e.g. Land, Bundesland, Strasse, ...).
    schema: dict[str, type[pl.DataType]] = {}
    for column in main_entity.value:
        schema[column.name] = _column_dtype(column)
    for column in Marktakteur:
        schema[f"Marktakteur_{column.name}"] = _column_dtype(column)
    return schema
