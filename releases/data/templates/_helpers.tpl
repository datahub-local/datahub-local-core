{{- define "superset.secret" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "superset" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "postgresql.configMapJobSetup" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if hasPrefix .Release.Name $name }}
{{- printf "%s-%s" $name "postgresql-job-setup" | trunc -30 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s-%s" .Release.Name $name "postgresql-job-setup" | trunc -30 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "postgresql.jobSetup" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if hasPrefix .Release.Name $name }}
{{- printf "%s-%s-" $name "postgresql-job-setup" | trunc 63 | trimSuffix "-" | trimPrefix "-" }}
{{- else }}
{{- printf "%s-%s-%s-" .Release.Name $name "postgresql-job-setup" | trunc 63 | trimSuffix "-" | trimPrefix "-" }}
{{- end }}
{{- end }}