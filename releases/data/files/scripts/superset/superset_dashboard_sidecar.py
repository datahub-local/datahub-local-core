#!/usr/bin/env python3
"""Sidecar daemon that syncs Superset dashboards from Kubernetes ConfigMaps.

Mimics the Grafana dashboard sidecar: ConfigMaps labeled ``superset_dashboard=1``
carry Superset dashboard export bundles (the v1 ``.zip`` produced by the UI
export or ``superset export-dashboards``) in ``binaryData``. Every bundle is
imported through the Superset REST API (overwriting on change), marked as
externally managed so it cannot be modified from the Superset UI, and deleted
from Superset once its ConfigMap disappears. Objects modified through the API
are detected via their modification timestamp and reverted on the next cycle.

Supported ConfigMap annotations:
  superset-dashboard/tags:          comma-separated tags applied to the
                                    dashboards (requires TAGGING_SYSTEM)
  superset-dashboard/certified-by:  certification badge for dashboards/charts
  superset-dashboard/publish:       "false" imports the dashboards as drafts
                                    (default is published)
"""

import base64
import hashlib
import io
import logging
import os
import pathlib
import time
import zipfile

import requests
import yaml

ADMIN_USERNAME = os.environ.get("SIDECAR_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("SIDECAR_ADMIN_PASSWORD", "admin")
LABEL_SELECTOR = os.environ.get("SIDECAR_LABEL_SELECTOR", "superset_dashboard=1")
# "" watches the namespace of the pod, "ALL" watches every namespace and a
# comma-separated list watches those namespaces
NAMESPACE = os.environ.get("SIDECAR_NAMESPACE", "")
SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://localhost:8088")
SYNC_INTERVAL = int(os.environ.get("SIDECAR_SYNC_INTERVAL", "60"))

ANNOTATION_PREFIX = "superset-dashboard/"
EXTERNAL_URL_PREFIX = "k8s-configmap://"
HEARTBEAT_FILE = "/tmp/superset-dashboard-sidecar-alive"
KUBERNETES_URL = os.environ.get("KUBERNETES_URL", "https://kubernetes.default.svc")
SERVICE_ACCOUNT_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"

logger = logging.getLogger("superset_dashboard_sidecar")


def list_dashboard_configmaps():
    with open(f"{SERVICE_ACCOUNT_DIR}/token") as token_file:
        token = token_file.read().strip()

    if NAMESPACE == "ALL":
        paths = ["/api/v1/configmaps"]
    elif NAMESPACE:
        paths = [f"/api/v1/namespaces/{ns.strip()}/configmaps" for ns in NAMESPACE.split(",") if ns.strip()]
    else:
        with open(f"{SERVICE_ACCOUNT_DIR}/namespace") as namespace_file:
            paths = [f"/api/v1/namespaces/{namespace_file.read().strip()}/configmaps"]

    items = []
    for path in paths:
        response = requests.get(
            f"{KUBERNETES_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params={"labelSelector": LABEL_SELECTOR},
            verify=f"{SERVICE_ACCOUNT_DIR}/ca.crt",
            timeout=30,
        )
        response.raise_for_status()
        items.extend(response.json()["items"])
    return items


def collect_bundles():
    """Return {source url: bundle entry} for every dashboard bundle found."""
    bundles = {}
    for configmap in list_dashboard_configmaps():
        namespace = configmap["metadata"]["namespace"]
        name = configmap["metadata"]["name"]
        annotations = configmap["metadata"].get("annotations") or {}
        options = {
            "tags": tuple(
                tag.strip()
                for tag in annotations.get(f"{ANNOTATION_PREFIX}tags", "").split(",")
                if tag.strip()
            ),
            "certified_by": annotations.get(f"{ANNOTATION_PREFIX}certified-by"),
            "publish": annotations.get(f"{ANNOTATION_PREFIX}publish", "true").lower() != "false",
        }
        for key, content in (configmap.get("binaryData") or {}).items():
            if key.endswith(".zip"):
                source = f"{EXTERNAL_URL_PREFIX}{namespace}/{name}/{key}"
                bundles[source] = {"bytes": base64.b64decode(content), "options": options}
            else:
                logger.warning("Ignoring %s/%s key %s: not a .zip export bundle", namespace, name, key)
        for key in configmap.get("data") or {}:
            logger.warning(
                "Ignoring %s/%s key %s: only v1 .zip export bundles in binaryData are supported",
                namespace, name, key,
            )
    return bundles


def is_managed_entry(file_name):
    """True for the dashboard and chart yaml files of an export bundle."""
    parts = file_name.split("/")
    return len(parts) == 3 and parts[1] in ("dashboards", "charts") and parts[2].endswith(".yaml")


def extract_uuids(bundle_bytes):
    """Return the dashboard and chart uuids declared in an export bundle."""
    dashboard_uuids, chart_uuids = set(), set()
    with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as bundle:
        for file_name in bundle.namelist():
            if is_managed_entry(file_name):
                config = yaml.safe_load(bundle.read(file_name))
                target = dashboard_uuids if file_name.split("/")[1] == "dashboards" else chart_uuids
                target.add(str(config["uuid"]))
    return dashboard_uuids, chart_uuids


def prepare_bundle(bundle_bytes, source, options):
    """Rewrite a bundle locking its dashboards and charts and applying options."""
    prepared = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as original, \
            zipfile.ZipFile(prepared, "w", zipfile.ZIP_DEFLATED) as target:
        for file_name in original.namelist():
            content = original.read(file_name)
            parts = file_name.split("/")
            if len(parts) == 2 and parts[1] == "metadata.yaml":
                # The assets import endpoint only accepts bundles of type "assets"
                config = yaml.safe_load(content)
                config["type"] = "assets"
                content = yaml.safe_dump(config).encode()
            elif is_managed_entry(file_name):
                config = yaml.safe_load(content)
                config["is_managed_externally"] = True
                config["external_url"] = source
                if options["certified_by"]:
                    config["certified_by"] = options["certified_by"]
                if file_name.split("/")[1] == "dashboards":
                    config["published"] = options["publish"]
                    if options["tags"]:
                        config["tags"] = list(options["tags"])
                content = yaml.safe_dump(config).encode()
            target.writestr(file_name, content)
    return prepared.getvalue()


class SupersetClient:
    """Minimal Superset REST API client."""

    def __init__(self, base_url, username, password):
        self.session = requests.Session()

        response = self.session.post(
            f"{base_url}/api/v1/security/login",
            json={"username": username, "password": password, "provider": "db", "refresh": False},
            timeout=30,
        )
        response.raise_for_status()
        self.session.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

        response = self.session.get(f"{base_url}/api/v1/security/csrf_token/", timeout=30)
        response.raise_for_status()
        self.session.headers["X-CSRFToken"] = response.json()["result"]
        self.session.headers["Referer"] = base_url

        self.base_url = base_url

    def import_bundle(self, bundle_bytes, file_name):
        # /api/v1/dashboard/import/ never overwrites existing charts and
        # datasets; the assets import overwrites every object type
        response = self.session.post(
            f"{self.base_url}/api/v1/assets/import/",
            files={"bundle": (file_name, io.BytesIO(bundle_bytes), "application/zip")},
            timeout=300,
        )
        response.raise_for_status()

    def list_managed(self, resource):
        """Return {uuid: {id, changed_on}} of every externally managed dashboard or chart."""
        managed, page = {}, 0
        while True:
            query = f"(columns:!(id,uuid,is_managed_externally,changed_on_utc),page:{page},page_size:100)"
            response = self.session.get(
                f"{self.base_url}/api/v1/{resource}/", params={"q": query}, timeout=30
            )
            response.raise_for_status()
            result = response.json()["result"]
            if not result:
                return managed
            for item in result:
                if item.get("is_managed_externally"):
                    managed[str(item["uuid"])] = {"id": item["id"], "changed_on": item["changed_on_utc"]}
            page += 1

    def delete(self, resource, object_id):
        response = self.session.delete(f"{self.base_url}/api/v1/{resource}/{object_id}", timeout=30)
        response.raise_for_status()


def current_stamps(state, dashboards, charts):
    """Return {uuid: changed_on} of a bundle's objects as currently in Superset."""
    stamps = {u: dashboards[u]["changed_on"] for u in state["dashboard_uuids"] if u in dashboards}
    stamps.update({u: charts[u]["changed_on"] for u in state["chart_uuids"] if u in charts})
    return stamps


def sync(applied):
    client = SupersetClient(SUPERSET_URL, ADMIN_USERNAME, ADMIN_PASSWORD)
    bundles = collect_bundles()
    dashboards = client.list_managed("dashboard")
    charts = client.list_managed("chart")

    imported = failed = False
    desired_dashboard_uuids, desired_chart_uuids = set(), set()
    for source, entry in sorted(bundles.items()):
        try:
            dashboard_uuids, chart_uuids = extract_uuids(entry["bytes"])
            desired_dashboard_uuids |= dashboard_uuids
            desired_chart_uuids |= chart_uuids

            digest = hashlib.sha256(
                entry["bytes"] + repr(sorted(entry["options"].items())).encode()
            ).hexdigest()

            previous = applied.get(source)
            if previous and previous["digest"] == digest:
                if dashboard_uuids <= dashboards.keys() and chart_uuids <= charts.keys():
                    if current_stamps(previous, dashboards, charts) == previous["stamps"]:
                        continue
                    logger.info("Drift detected on %s, reverting", source)

            logger.info("Importing %s", source)
            client.import_bundle(
                prepare_bundle(entry["bytes"], source, entry["options"]), source.rsplit("/", 1)[-1]
            )
            applied[source] = {
                "digest": digest,
                "dashboard_uuids": dashboard_uuids,
                "chart_uuids": chart_uuids,
                "stamps": None,
            }
            imported = True
        except Exception:
            logger.exception("Failed to import %s", source)
            applied.pop(source, None)
            failed = True

    # Drop state of sources whose ConfigMap entry no longer exists
    for source in list(applied):
        if source not in bundles:
            del applied[source]

    if imported:
        dashboards = client.list_managed("dashboard")
        charts = client.list_managed("chart")

    # Record post-import modification timestamps for drift detection
    for state in applied.values():
        if state["stamps"] is None:
            state["stamps"] = current_stamps(state, dashboards, charts)

    if failed:
        # A bundle could not be processed, so the desired state is incomplete:
        # do not delete anything this cycle
        return

    # Delete dashboards and charts whose ConfigMap entry no longer exists
    for resource, managed, desired in (
        ("dashboard", dashboards, desired_dashboard_uuids),
        ("chart", charts, desired_chart_uuids),
    ):
        for uuid, item in managed.items():
            if uuid not in desired:
                logger.info("Deleting stale %s %s (uuid %s)", resource, item["id"], uuid)
                try:
                    client.delete(resource, item["id"])
                except Exception:
                    logger.exception("Failed to delete %s %s", resource, item["id"])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
    applied = {}
    while True:
        try:
            sync(applied)
        except Exception:
            logger.exception("Dashboard sync failed")
        pathlib.Path(HEARTBEAT_FILE).touch()
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
