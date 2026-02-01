import json
import logging
import os
import functools
from json import JSONDecodeError

# Logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(log_format)
logger.addHandler(console_handler)

STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "/commafeed/data/job_setup_status.json")


def get_logger():
    return logger


def create_file(file: str, file_content: str, mask: int = 0o077):
    """
    Docstring for create_file

    :param file: Description
    :type file: str
    :param file_content: Description
    :type file_content: str
    """
    os.umask(mask)
    with open(file, "w+") as fd:
        fd.write(file_content)


def create_dir(dir: str):
    """
    Docstring for create_dir

    :param dir: Description
    :type dir: str
    """
    if not os.path.exists(dir):
        os.makedirs(dir)


def load_state():
    try:
        if os.path.exists(STATE_FILE_PATH):
            try:
                with open(STATE_FILE_PATH, "r") as f:
                    return json.load(f)
            except JSONDecodeError:
                return {}
    except Exception as e:
        logger.error(f"Failed to load state[{STATE_FILE_PATH}]: {e}")
    return {}


def save_state(state):
    try:
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save state[{STATE_FILE_PATH}]: {e}")


def is_step_completed(step_name):
    state = load_state()
    return state.get(step_name, False)


def mark_step_completed(step_name):
    state = load_state()
    state[step_name] = True
    save_state(state)


def step(step_name, exit_on_failure=True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not is_step_completed(step_name):
                logger.info(f"Starting step: {step_name}")
                try:
                    result = func(*args, **kwargs)
                    mark_step_completed(step_name)
                    logger.info(f"Completed step: {step_name}")
                    return result
                except Exception as e:
                    logger.error(f"Error occurred in step {step_name}: {e}")
                    if exit_on_failure:
                        exit(1)
                    else:
                        raise e
            else:
                logger.info(f"Step already completed: {step_name}")

        return wrapper

    return decorator