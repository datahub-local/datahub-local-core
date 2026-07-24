import logging
import os

import requests
import yaml

# Logging setup
logger = logging.getLogger("setup_miniflux")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(_handler)

# Configuration
MINIFLUX_URL = os.environ.get("MINIFLUX_URL", "http://localhost:8080").rstrip("/")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
CLEANUP_OLD = os.environ.get("MINIFLUX_CLEANUP_OLD", "true").lower() == "true"
CONFIG_FILE = os.environ.get("CONFIG_FILE", "/scripts/miniflux_config.yaml")

session = requests.Session()


def api(method, path, **kwargs):
    resp = session.request(method, f"{MINIFLUX_URL}{path}", **kwargs)
    if not resp.ok:
        # Miniflux returns the real reason in the body (e.g. {"error_message": ...});
        # surface it instead of a bare status code.
        raise requests.HTTPError(
            f"{resp.status_code} {resp.reason} for {method} {path}: {resp.text.strip()}",
            response=resp,
        )
    return resp.json() if resp.content else None


def get_categories():
    # {title: id}
    return {c["title"]: c["id"] for c in api("GET", "/v1/categories")}


def create_category(title):
    logger.info(f"Creating category: {title}")
    return api("POST", "/v1/categories", json={"title": title})["id"]


def get_feeds():
    # {feed_url: {id, title, category_id}}
    feeds = {}
    for f in api("GET", "/v1/feeds"):
        feeds[f["feed_url"]] = {
            "id": f["id"],
            "title": f["title"],
            "category_id": f.get("category", {}).get("id"),
        }
    return feeds


def create_feed(feed_url, category_id):
    logger.info(f"Subscribing to: {feed_url}")
    return api(
        "POST", "/v1/feeds", json={"feed_url": feed_url, "category_id": category_id}
    )["feed_id"]


def update_feed(feed_id, title, category_id):
    api(
        "PUT",
        f"/v1/feeds/{feed_id}",
        json={"title": title, "category_id": category_id},
    )


def configure_feeds():
    if not os.path.exists(CONFIG_FILE):
        raise Exception(f"{CONFIG_FILE} does not exist")

    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)

    categories_config = config.get("categories", {})

    # Reconcile categories
    categories = get_categories()
    for category_name in categories_config:
        if category_name not in categories:
            categories[category_name] = create_category(category_name)

    # Reconcile feeds (create missing, fix title/category on existing)
    existing_feeds = get_feeds()
    wanted_urls = set()
    failed_feeds = []
    for category_name, feeds in categories_config.items():
        category_id = categories[category_name]
        for feed in feeds:
            feed_url = feed.get("url")
            feed_title = feed.get("title")
            if not feed_url:
                continue
            wanted_urls.add(feed_url)

            current = existing_feeds.get(feed_url)
            try:
                if current is None:
                    feed_id = create_feed(feed_url, category_id)
                    if feed_title:
                        update_feed(feed_id, feed_title, category_id)
                elif (feed_title and current["title"] != feed_title) or current[
                    "category_id"
                ] != category_id:
                    logger.info(f"Updating feed: {feed_title or feed_url}")
                    update_feed(
                        current["id"], feed_title or current["title"], category_id
                    )
            except requests.RequestException as e:
                # A single unreachable/broken feed (Miniflux replies 500) must not
                # abort the whole reconciliation. Record it and keep going.
                logger.warning(f"Skipping feed {feed_title or feed_url}: {e}")
                failed_feeds.append(feed_url)

    if failed_feeds:
        logger.warning(
            f"{len(failed_feeds)} feed(s) could not be subscribed: "
            + ", ".join(failed_feeds)
        )

    if not CLEANUP_OLD:
        return

    # Remove feeds no longer in config
    logger.info("Cleaning up old feeds and categories...")
    for feed_url, feed in existing_feeds.items():
        if feed_url not in wanted_urls:
            logger.info(f"Unsubscribing from feed: {feed['title']}")
            api("DELETE", f"/v1/feeds/{feed['id']}")

    # Remove empty categories no longer in config (skip any still holding feeds,
    # e.g. Miniflux's default category)
    for category in api("GET", "/v1/categories?counts=true"):
        if category["title"] not in categories_config and not category.get(
            "feed_count", 0
        ):
            logger.info(f"Deleting category: {category['title']}")
            api("DELETE", f"/v1/categories/{category['id']}")


def main():
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise Exception("Admin credentials not provided")

    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)
    configure_feeds()
    logger.info("Feed configuration completed.")


if __name__ == "__main__":
    main()
