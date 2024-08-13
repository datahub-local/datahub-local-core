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

{{- define "grafana.configMapDataSource" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "grafana-datasource" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "prometheus.ruleName" -}}
{{- $top := index . 0 -}}
{{- $prefix := default $top.Chart.Name $top.Values.nameOverride }}
{{- $name := index . 1 -}}
{{- printf "%s-%s" $prefix $name | trunc 63 | trimSuffix "-" }}
{{- end }}

