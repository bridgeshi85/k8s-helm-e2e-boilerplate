{{/*
===========================================================================
SECTION 1: Naming & Chart Standardization
===========================================================================
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "taskflow.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "taskflow.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "taskflow.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
===========================================================================
SECTION 2: Labels & Selectors
===========================================================================
*/}}

{{/*
Common labels (Include standard K8s recommendations)
*/}}
{{- define "taskflow.labels" -}}
helm.sh/chart: {{ include "taskflow.chart" . }}
{{ include "taskflow.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels (Immutable labels used for Deployment selectors)
*/}}
{{- define "taskflow.selectorLabels" -}}
app.kubernetes.io/name: {{ include "taskflow.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
===========================================================================
SECTION 3: App Configuration Helpers
===========================================================================
*/}}

{{/*
Redis Hostname
Return the fixed service name for Redis Master
*/}}
{{/*
Database Connection URL (PostgreSQL)
Constructs the full SQLAlchemy connection string using values from sub-chart
Format: postgresql://user:password@host:port/dbname
*/}}
{{- define "taskflow.databaseUrl" -}}
{{- $user := .Values.postgresql.auth.username -}}
{{- $pass := .Values.postgresql.auth.password -}}
{{- $db   := .Values.postgresql.auth.database -}}
postgresql://{{ $user }}:{{ $pass }}@{{ .Values.postgresql.fullnameOverride }}:5432/{{ $db }}
{{- end }}