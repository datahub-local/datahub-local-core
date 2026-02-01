import os
import requests
import yaml
import hashlib

from utils import step, logger, load_state, save_state

# Configuration
COMMAFEED_URL = os.environ.get("COMMAFEED_URL", "http://localhost:8082")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "30"))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", "10"))
CLEANUP_OLD = os.environ.get("COMMAFEED_CLEANUP_OLD", "true").lower() == "true"
CONFIG_FILE = "/scripts/commafeed_config.yaml"

session = requests.Session()


def setup_auth():
    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)


@step("commafeed_initial_setup")
def initial_setup():
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        logger.warning("Admin credentials not provided, skipping initial setup.")
        return False

    logger.info(f"Performing initial setup with admin user: {ADMIN_USERNAME}")
    payload = {
        "name": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD,
        "email": ADMIN_EMAIL or "admin@example.com",
    }
    resp = session.post(f"{COMMAFEED_URL}/rest/user/initialSetup", json=payload)

    if resp.status_code == 200:
        logger.info("Initial setup completed successfully!")
    else:
        try:
            data = resp.json()
            if not data.get("initialSetupRequired", True):
                logger.info("Initial setup already done")
            else:
                raise Exception(f"Initial setup failed: {data}")
        except Exception as e:
            raise Exception(f"Initial setup failed", e)


def get_category_id(category_name):
    resp = session.get(f"{COMMAFEED_URL}/rest/category/get")
    if resp.status_code != 200:
        return None
    root_category = resp.json()
    for child in root_category.get("children", []):
        if child.get("name") == category_name:
            return child.get("id")
    return None


def create_category(category_name):
    category_id = get_category_id(category_name)
    if category_id:
        return category_id

    payload = {"name": category_name, "parentId": "all"}
    response = session.post(f"{COMMAFEED_URL}/rest/category/add", json=payload)

    response.raise_for_status()

    return get_category_id(category_name)


def subscribe_feed(feed_url, feed_title, category_id):
    logger.info(f"Subscribing to: {feed_title}")
    payload = {"url": feed_url, "title": feed_title, "categoryId": category_id}
    response = session.post(f"{COMMAFEED_URL}/rest/feed/subscribe", json=payload)
    response.raise_for_status()


def get_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()


def configure_feeds():
    if not os.path.exists(CONFIG_FILE):
        raise Exception(f"{CONFIG_FILE} does not exist")

    current_hash = get_file_hash(CONFIG_FILE)
    state = load_state()
    if state.get("config_hash") == current_hash:
        logger.info("Feed configuration hash matches, skipping.")
        return

    try:
        with open(CONFIG_FILE, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        raise Exception("Configuration parsing failed", e)

    categories_config = config.get("categories", {})
    logger.info("Configuring feeds...")
    for category_name, feeds in categories_config.items():
        category_id = create_category(category_name)
        if not category_id:
            logger.warning(f"Could not find/create category {category_name}")
            continue

        for feed in feeds:
            feed_url = feed.get("url")
            feed_title = feed.get("title")
            if feed_url:
                subscribe_feed(feed_url, feed_title, category_id)

    # Cleanup if requested
    if CLEANUP_OLD:
        logger.info("Cleaning up old categories and feeds...")

        resp = session.get(f"{COMMAFEED_URL}/rest/category/get")
        if resp.status_code == 200:
            root_category = resp.json()
            for child in root_category.get("children", []):
                cat_name = child.get("name")
                cat_id = child.get("id")
                if cat_name not in categories_config:
                    logger.info(f"Deleting category: {cat_name}")

                    response = session.post(
                        f"{COMMAFEED_URL}/rest/category/delete", json={"id": cat_id}
                    )
                    response.raise_for_status()
                else:
                    # Check feeds in this category
                    config_feeds_urls = [
                        f.get("url") for f in categories_config[cat_name]
                    ]
                    for feed in child.get("feeds", []):
                        if feed.get("feedUrl") not in config_feeds_urls:
                            logger.info(f"Unsubscribing from feed: {feed.get('name')}")

                            response = session.post(
                                f"{COMMAFEED_URL}/rest/feed/unsubscribe",
                                json={"id": feed.get("id")},
                            )
                            response.raise_for_status()

    state["config_hash"] = current_hash
    save_state(state)


def main():
    initial_setup()

    setup_auth()

    configure_feeds()


if __name__ == "__main__":
    main()
