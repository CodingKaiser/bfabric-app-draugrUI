"""
Session clients for the B-Fabric instance the app was launched from.

Authentication is the library's: exchanging the launch token establishes an OAuth
session per instance, holding a client for the logged-in user and one for the app's
service account. These helpers only rebuild the typed token context from the dict
that survives the dcc.Store round trip, and hand back the matching client.

Nothing here reads ~/.bfabricpy.yml any more, and there is no password in the
token — both went away with the move to OAuth.
"""

from bfabric import Bfabric
from bfabric.oauth import UrlTokenContext
from bfabric_web_apps import bfabric_interface
from bfabric_web_apps import get_logger as library_get_logger
from bfabric_web_apps.objects.Logger import Logger


def as_token_data(token_data) -> UrlTokenContext:
    """
    Return the typed token context, rebuilding it from the dcc.Store dict if needed.

    Only the model's fields survive the round trip through the store, so derived
    values such as `base_url` and `is_employee` are only available on the model.
    """
    if isinstance(token_data, UrlTokenContext):
        return token_data
    return UrlTokenContext.model_validate(token_data)


def get_user_wrapper(token_data) -> Bfabric:
    """
    Return the session's Bfabric client for the logged-in user.

    The run and lane data this app reads runs with the user's own permissions,
    not the service account's.

    Raises:
        RuntimeError: If the OAuth session has expired and the user has to re-open
            the app from B-Fabric.
    """
    return bfabric_interface.get_wrapper(as_token_data(token_data))


def get_logger(token_data) -> Logger:
    """Return a Logger that writes audit entries under the service account."""
    return library_get_logger(as_token_data(token_data))
