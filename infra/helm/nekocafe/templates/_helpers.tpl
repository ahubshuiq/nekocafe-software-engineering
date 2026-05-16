{{/*
Common labels
*/}}
{{- define "nekocafe.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Namespace
*/}}
{{- define "nekocafe.namespace" -}}
{{ .Values.namespace | default .Release.Namespace }}
{{- end }}
