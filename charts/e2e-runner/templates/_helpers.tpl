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

{{/*
===========================================================================
SECTION 4: Pytest Arguments Builder
===========================================================================
*/}}

{{/*
Build pytest arguments
*/}}
{{- define "e2e-runner.pytestArgs" -}}
{{- $args := list }}
# 基础参数
{{- $args = append $args "-v" }}
{{- $args = append $args "--alluredir=$(ALLURE_RESULTS_DIR)" }}
# Marker 筛选
{{- if .Values.test.pytest.markers }}
{{- $args = append $args (printf "-m=%s" .Values.test.pytest.markers) }}
{{- end }}
# 并发配置
{{- if gt (int .Values.test.pytest.workers) 1 }}
{{- $args = append $args (printf "-n=%d" (int .Values.test.pytest.workers)) }}
{{- end }}
# 失败重试
{{- if gt (int .Values.test.pytest.reruns) 0 }}
{{- $args = append $args (printf "--reruns=%d" (int .Values.test.pytest.reruns)) }}
{{- if gt (int .Values.test.pytest.rerunsDelay) 0 }}
{{- $args = append $args (printf "--reruns-delay=%d" (int .Values.test.pytest.rerunsDelay)) }}
{{- end }}
{{- end }}
# 最大失败次数
{{- if gt (int .Values.test.pytest.maxFailures) 0 }}
{{- $args = append $args (printf "--maxfail=%d" (int .Values.test.pytest.maxFailures)) }}
{{- end }}
# 额外参数
{{- range .Values.test.pytest.extraArgs }}
{{- $args = append $args . }}
{{- end }}
# 测试路径
{{- $args = append $args .Values.test.pytest.testPath }}
# 输出结果
{{- join " " $args }}
{{- end }}