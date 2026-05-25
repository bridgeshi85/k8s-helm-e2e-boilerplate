{{/*
===========================================================================
SECTION 1: Naming & Chart Standardization
===========================================================================
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "e2e-runner.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "e2e-runner.fullname" -}}
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
{{- define "e2e-runner.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
===========================================================================
SECTION 2: Labels & Selectors
===========================================================================
*/}}

{{/*
Common labels
*/}}
{{- define "e2e-runner.labels" -}}
helm.sh/chart: {{ include "e2e-runner.chart" . }}
{{ include "e2e-runner.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "e2e-runner.selectorLabels" -}}
app.kubernetes.io/name: {{ include "e2e-runner.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
===========================================================================
SECTION 3: PVC Name Helper
===========================================================================
*/}}

{{/*
PVC Name
*/}}
{{- define "e2e-runner.pvcName" -}}
{{- include "e2e-runner.fullname" . }}-artifacts
{{- end }}