{{- define "grafana.jobSetupGrafana" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "grafana-job-setup" | trunc -30 | trimSuffix "-" }}
{{- end }}

{{- define "grafana.configMapJobSetupGrafana" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s-" $name "grafana-job-setup" | trunc 63 | trimSuffix "-" | trimPrefix "-" }}
{{- end }}

{{- define "grafana.configMapGrafanaDashboard" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "grafana-dashboard" | trunc 63 | trimSuffix "-" }}
{{- end }}