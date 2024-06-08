{{- define "superset.secret" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "superset" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "postgresql.configMapJobSetup" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "postgresql-job-setup" | trunc -30 | trimSuffix "-" }}
{{- end }}

{{- define "postgresql.jobSetup" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s-" $name "postgresql-job-setup" | trunc -40 | trimSuffix "-" | trimPrefix "-" }}
{{- end }}