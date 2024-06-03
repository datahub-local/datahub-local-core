{{- define "trino.ingressRoute" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if hasPrefix .Release.Name $name }}
{{- printf "%s-%s" $name "trino-console" | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s-%s" .Release.Name $name "trino-console" | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "trino.service" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if hasPrefix .Release.Name $name }}
{{- printf "%s-%s" $name "trino" | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s-%s" .Release.Name $name "trino" | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}