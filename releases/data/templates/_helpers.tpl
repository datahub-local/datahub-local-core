{{- define "name" -}}
{{ default .Chart.Name .Values.nameOverride }}
{{- end }}

{{- define "superset.secret" -}}
{{- $name := (include "name" .) }}
{{- printf "%s-%s" $name "superset" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "superset.serviceAccount" -}}
{{- $name := (include "name" .) }}
{{- printf "%s-%s" $name "superset" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "superset.configMapSupersetDashboard" -}}
{{- $name := (include "name" .) }}
{{- printf "%s-%s" $name "superset-dashboard" | trunc 63 | trimSuffix "-" }}
{{- end }}
