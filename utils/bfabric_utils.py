"""
Local overrides for Bfabric wrappers and logger.

- Power user wrapper: reads from ~/.bfabricpy.yml (for log writes)
- User wrapper: built from token credentials (for data reads)
- Logger: uses power user wrapper for flushing logs
"""

import os
from bfabric import Bfabric, BfabricAuth, BfabricClientConfig
from bfabric.config.config_data import ConfigData
from bfabric_web_apps.objects.Logger import Logger

CONFIG_FILE_PATH = os.path.expanduser("~/.bfabricpy.yml")


def get_power_user_wrapper() -> Bfabric:
    """Return a Bfabric wrapper using credentials from ~/.bfabricpy.yml."""
    return Bfabric.from_config(config_path=CONFIG_FILE_PATH)


def get_user_wrapper(token_data: dict) -> Bfabric:
    """
    Return a Bfabric wrapper using the logged-in user's credentials from the token.

    This matches the old token_response_to_bfabric() behavior: API calls
    run with the user's own permissions, not the power user's.
    """
    auth = BfabricAuth(
        login=token_data.get("user_data"),
        password=token_data.get("userWsPassword"),
    )
    client_config = BfabricClientConfig(base_url=token_data.get("webbase_data"))
    config_data = ConfigData(client=client_config, auth=auth)
    return Bfabric(config_data=config_data)


def get_logger(token_data: dict) -> Logger:
    """
    Create a Logger whose power_user_wrapper reads from ~/.bfabricpy.yml
    instead of the framework's .env-based credentials.
    """
    jobid = token_data.get("jobId")
    username = token_data.get("user_data", "unknown")
    base_url = token_data.get("webbase_data", "")

    logger = Logger(jobid=jobid, username=username, base_url=base_url)
    # Override the wrapper with one from ~/.bfabricpy.yml
    logger.power_user_wrapper = get_power_user_wrapper()
    return logger
