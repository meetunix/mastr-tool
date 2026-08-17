{{/*
Expand the name of the chart.
*/}}
{{- define "mastr-tool.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name (release-name + chart-name).
*/}}
{{- define "mastr-tool.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart name and version label.
*/}}
{{- define "mastr-tool.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "mastr-tool.labels" -}}
helm.sh/chart: {{ include "mastr-tool.chart" . }}
{{ include "mastr-tool.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "mastr-tool.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mastr-tool.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the database Secret used to populate DB_USER/DB_PASSWORD.
- standalone: the chart creates it from .Values.database.standalone.* values.
- cnpg: by default an existing user-provided Secret is referenced.
*/}}
{{- define "mastr-tool.dbSecretName" -}}
{{- if eq .Values.database.mode "standalone" }}
{{- include "mastr-tool.fullname" . }}-db
{{- else if .Values.database.existingSecret }}
{{- .Values.database.existingSecret }}
{{- else }}
{{- include "mastr-tool.fullname" . }}-db
{{- end }}
{{- end }}

{{/*
Resolve the DB host.
- standalone: the in-chart Postgres Service name.
- cnpg: .Values.database.host (must be set by the user).
*/}}
{{- define "mastr-tool.dbHost" -}}
{{- if eq .Values.database.mode "standalone" }}
{{- include "mastr-tool.fullname" . }}-db
{{- else }}
{{- required (printf "database.host is required when database.mode=%s" .Values.database.mode) .Values.database.host }}
{{- end }}
{{- end }}

{{/*
Resolve the DB user.
*/}}
{{- define "mastr-tool.dbUser" -}}
{{- if eq .Values.database.mode "standalone" }}
{{- .Values.database.standalone.user }}
{{- else }}
{{- required (printf "database.user is required when database.mode=%s" .Values.database.mode) .Values.database.user }}
{{- end }}
{{- end }}

{{/*
Resolve the DB name.
*/}}
{{- define "mastr-tool.dbName" -}}
{{- if eq .Values.database.mode "standalone" }}
{{- .Values.database.standalone.name }}
{{- else }}
{{- .Values.database.name }}
{{- end }}
{{- end }}
