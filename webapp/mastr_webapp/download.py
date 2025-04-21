from dash import html, dcc, callback, Input, Output
from .styles import download_dropdown_style
from .constants import EnergySources, ENTITY_MAP, DownloadFormats, DEFAULT_ENTITY_VALUE
from .util import get_download_url
from .util_web import RESTClient

download_div = html.Div(
    id="div-download",
    children=[
        html.Div(
            dcc.Dropdown(
                [es.value for es in EnergySources],
                value=EnergySources.WIND.value,
                id="dropdown-download-source",
            ),
            id="div-download-source",
            style=download_dropdown_style,
        ),
        html.Div(
            dcc.Dropdown(
                ["None"],
                value="DE",
                id="dropdown-download-entity",
            ),
            id="div-download-entity",
            style=download_dropdown_style,
        ),
        html.Div(
            dcc.Dropdown(
                [{"label": fm.name, "value": fm.value} for fm in DownloadFormats],
                value=DownloadFormats.CSV.value,
                id="dropdown-download-format",
            ),
            id="div-energy-format",
            style=download_dropdown_style,
        ),
        html.Div(
            html.A(
                html.Button("Download", id="button-dynamic-download", className="mastr-button"),
                id="link-dynamic-download",
            ),
            id="div-dynamic-download",
        ),
    ],
)


@callback(
    Output("dropdown-download-entity", "options"),
    Input("dropdown-download-source", "value"),
)
def set_download_entity(value):
    entity = ENTITY_MAP[EnergySources(value)]
    return [{"label": v, "value": k} for k, v in entity.items()]


@callback(
    Output("button-dynamic-download", "children"),
    Output("link-dynamic-download", "href"),
    Input("dropdown-download-source", "value"),
    Input("dropdown-download-entity", "value"),
    Input("dropdown-download-format", "value"),
)
def set_download_dynamic_button(source, entity_key, format):
    entities = ENTITY_MAP[EnergySources(source)]
    if None not in (source, entity_key, format) and entity_key in entities:
        url = get_download_url(EnergySources(source), entities[entity_key], DownloadFormats(format))
        rest_client = RESTClient()
        file_size = rest_client.get_file_size_mib(url)
        if file_size is None:
            return f"{DownloadFormats(format).name} nicht verfügbar", url
        return f"{DownloadFormats(format).name} ({file_size:.2f} MiB)", url
    return "Keine Übereinstimmung", ""
