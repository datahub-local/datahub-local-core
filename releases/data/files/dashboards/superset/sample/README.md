# Sample Superset dashboard

Source of `../sample.zip`, a Superset v1 dashboard export bundle deployed by the
dashboard sidecar (see `templates/superset_dashboard.yaml`). It renders synthetic
data through a virtual dataset on the Trino `memory` catalog, so it works without
any tables existing.

After editing the YAML files, rebuild the bundle:

```bash
cd releases/data/files/dashboards/superset/sample
python3 -c "
import zipfile, pathlib
with zipfile.ZipFile('../sample.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(pathlib.Path('dashboard_export').rglob('*.yaml')):
        bundle.write(path)
"
```
