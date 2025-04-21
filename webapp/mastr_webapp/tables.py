import json

import pandas as pd
from datetime import datetime
from dash import html, callback, Input, Output, dcc, no_update, State
from dash.dcc import Download
from dash.dash_table import DataTable
from .strings import *
from .util import *
from .util_web import RESTClient


def get_static_table() -> DataTable:
    return DataTable(
        id="static-table",
        editable=False,
        filter_action="native",
        sort_action="native",
        sort_mode="multi",
        column_selectable="single",
        row_selectable="multi",
        row_deletable=False,
        selected_columns=[],
        selected_rows=[],
        page_action="native",
        page_current=0,
        style_as_list_view=True,
        page_size=20,
        # style_table={'overflowX': 'auto', 'minWidth': '100%', 'maxWidth' : "100%"},
        style_table={"minWidth": "100%", "maxWidth": "100%"},
        fixed_columns={"headers": True},
        # fixed_rows={'headers': True},
        style_header={
            "backgroundColor": "rgb(210, 210, 210)",
            "color": "black",
            "fontWeight": "bold",
            "textAlign": "center",
        },
        style_data_conditional=[
            {
                "if": {"row_index": "odd"},
                "backgroundColor": "rgb(220, 220, 220)",
            },
            {
                "if": {"state": "selected"},
                "backgroundColor": "#00cc99",
                "border": "0 px solid white",
            },
        ],
        style_cell={
            "padding-right": "10px",
            "padding-left": "10px",
            "minWidth": "240px",
            "width": "240px",
            "maxWidth": "240px",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
        },
        tooltip_delay=500,
        tooltip_duration=None,
    )


# update static table via dropdown
@callback(
    Output("static-table", "data"),
    Output("static-table", "columns"),
    Output("static-table", "tooltip_data"),
    Output("stored-static-table", "data"),
    Input("state-table-dropdown", "value"),
)
def update_output(value):
    table_url = static_table_states.inverse[value].value
    df = pd.read_csv(table_url)
    columns = [{"name": i, "id": i, "deletable": False, "selectable": False} for i in df.columns]
    tooltip_data = [
        {column: {"value": str(value), "type": "markdown"} for column, value in row.items()}
        for row in df.to_dict("records")
    ]

    json_to_store = df.to_json()
    return df.to_dict("records"), columns, tooltip_data, json_to_store


def get_static_table_download() -> html.Div:
    return html.Div(
        id="div-static-download-buttons",
        children=[
            html.Div(
                [
                    html.A(
                        html.Button(
                            children="Datensatz als CSV (.csv)",
                            id="button-static-download-dataset",
                            className="mastr-button",
                        ),
                        href="https://mastr-static.nachtsieb.de/exports/dump_date",
                        id="link-static-download-dataset",
                    ),
                ]
            ),
            html.Div(
                [
                    html.A(
                        html.Button(
                            children="Datensatz als Excel (.xlsx)",
                            id="button-static-download-excel",
                            className="mastr-button",
                        ),
                        href="https://mastr-static.nachtsieb.de/exports/dump_date",
                        id="link-static-download-excel",
                    ),
                ]
            ),
            html.Div(
                [
                    html.A(
                        html.Button(
                            children="Datensatz als Parquet (.parq)",
                            id="button-static-download-parquet",
                            className="mastr-button",
                        ),
                        href="https://mastr-static.nachtsieb.de/exports/dump_date",
                        id="link-static-download-parquet",
                    ),
                ]
            ),
            html.Div(
                [
                    dcc.Loading(
                        id="loading-button-static-selected",
                        children=[
                            html.Button(
                                children="Auswahl als CSV (0)})",
                                id="button-static-selected",
                                className="mastr-button",
                            ),
                            Download(id="download-static-selected"),
                        ],
                        type="circle",
                        delay_show=300,
                        className="loading-button",
                        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                    )
                ]
            ),
            html.Div(
                [
                    dcc.Loading(
                        id="loading-button-static-filtered",
                        children=[
                            html.Button(
                                children="Filterergebnis als CSV",
                                id="button-static-filtered",
                                className="mastr-button",
                            ),
                            Download(id="download-static-filtered"),
                        ],
                        type="circle",
                        delay_show=300,
                        className="loading-button",
                        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                    )
                ],
            ),
            html.Div(
                html.Button(
                    children="Auswahl aufheben",
                    id="button-static-erase",
                    className="mastr-button",
                )
            ),
        ],
        style={"display": "flex"},
    )


@callback(
    Output("link-static-download-dataset", "href"),
    Output("button-static-download-dataset", "children"),
    Output("link-static-download-excel", "href"),
    Output("button-static-download-excel", "children"),
    Output("link-static-download-parquet", "href"),
    Output("button-static-download-parquet", "children"),
    Input("state-table-dropdown", "value"),
)
def update_download_buttons(value):
    table_url = static_table_states.inverse[value].value
    rest_client = RESTClient()
    excel_url = replace_filetype_on_url(table_url, ".xlsx")
    parq_url = replace_filetype_on_url(table_url, ".parq")

    return (
        table_url,
        f"Datensatz als CSV (.csv, {rest_client.get_file_size_mib(table_url):.2f} MiB)",
        excel_url,
        f"Datensatz als Excel (.xlsx, {rest_client.get_file_size_mib(excel_url):.2f} MiB)",
        parq_url,
        f"Datensatz als Parquet (.parq, {rest_client.get_file_size_mib(parq_url):.2f} MiB)",
    )


@callback(
    Output("button-static-selected", "children"),
    Output("stored-selected-rows", "data"),
    Input("static-table", "derived_virtual_selected_rows"),
    prevent_initial_call=True,
)
def update_button_row_counter(rows):
    if rows is None:
        return no_update
    else:
        return f"Auswahl als CSV ({len(rows)})", json.dumps(rows)


# download selected rows
@callback(
    Output("download-static-selected", "data"),
    Input("button-static-selected", "n_clicks"),
    State("stored-static-table", "data"),
    State("stored-selected-rows", "data"),
    prevent_initial_call=True,
)
def download_rows(n_clicks, stored_table_data, stored_selected_rows):
    if stored_selected_rows is None:
        return no_update
    rows = json.loads(stored_selected_rows)

    if len(rows) <= 0:
        return no_update

    rows = sorted(rows)

    df = pd.DataFrame(json.loads(stored_table_data))
    df = df.iloc[rows]
    filename = f"mastr-tool-export-{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    return dcc.send_data_frame(df.to_csv, filename, index=False)


# download filtered rows
@callback(
    Output("download-static-filtered", "data"),
    Output("button-static-filtered", "n_clicks"),
    Input("button-static-filtered", "n_clicks"),
    Input("static-table", "derived_virtual_indices"),
    State("stored-static-table", "data"),
    prevent_initial_call=True,
)
def download_rows(n_clicks, filtered_row_ids, stored_table_data):
    if n_clicks is None:
        return no_update

    if filtered_row_ids is None:
        return no_update

    if len(filtered_row_ids) <= 0:
        return no_update

    filtered_rows = sorted(filtered_row_ids)

    df = pd.DataFrame(json.loads(stored_table_data))
    df = df.iloc[filtered_rows]
    filename = f"mastr-tool-export-{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    return dcc.send_data_frame(df.to_csv, filename, index=False), None


# erase selected rows
@callback(
    Output("static-table", "selected_rows"),
    Input("button-static-erase", "n_clicks"),
    prevent_initial_call=True,
)
def update_button_row_counter(n_clicks):
    if n_clicks is None:
        return no_update
    else:
        return []
