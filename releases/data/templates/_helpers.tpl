{{- define "superset.secret" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "superset" | trunc 63 | trimSuffix "-" }}
{{- end }}