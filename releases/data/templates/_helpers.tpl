{{- define "name" -}}
{{ default .Chart.Name .Values.nameOverride }}
{{- end }}

{{- define "superset.secret" -}}
{{- $name := (include "name" .) }}
{{- printf "%s-%s" $name "superset" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "postgresql.configMapJobSetup" -}}
{{- $name := (include "name" .) }}
{{- printf "%s-%s" $name "postgresql-job-setup" | trunc -63 | trimSuffix "-" }}
{{- end }}

{{- define "postgresql.jobSetup" -}}
{{- $name := (include "name" .) }}
{{- printf "%s-%s-" $name "postgresql-job-setup" | trunc -30 | trimSuffix "-" | trimPrefix "-" }}
{{- end }}
