{{- define "grafana.jobSetupGrafana" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if hasPrefix .Release.Name $name }}
{{- printf "%s-%s" $name "grafana-job-setup" | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s-%s" .Release.Name $name "grafana-job-setup" | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "grafana.configMapJobSetupGrafana" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if hasPrefix .Release.Name $name }}
{{- printf "%s-%s" $name "grafana-job-setup" | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s-%s" .Release.Name $name "grafana-job-setup" | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "grafana.configMapGrafanaDashboard" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if hasPrefix .Release.Name $name }}
{{- printf "%s-%s" $name "grafana-dashboard" | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s-%s" .Release.Name $name "grafana-dashboard" | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}