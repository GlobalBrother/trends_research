import logging
import os
from threading import Lock

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_initialized = False
_lock = Lock()


def init_runtime_secrets() -> None:
    """Load runtime secrets from Azure Key Vault, falling back to .env.

    This function is safe to call from multiple modules; initialization runs once
    per process.
    """
    global _initialized
    if _initialized:
        return

    with _lock:
        if _initialized:
            return

        kv_name = os.environ.get("KEY_VAULT_NAME", "").strip()
        if kv_name:
            try:
                from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
                from azure.keyvault.secrets import SecretClient

                mi_client_id = os.environ.get("MANAGED_IDENTITY_CLIENT_ID")
                credential = (
                    ManagedIdentityCredential(client_id=mi_client_id)
                    if mi_client_id
                    else DefaultAzureCredential()
                )
                client = SecretClient(
                    vault_url=f"https://{kv_name}.vault.azure.net",
                    credential=credential,
                )
                for prop in client.list_properties_of_secrets():
                    secret = client.get_secret(prop.name)
                    os.environ[secret.name.replace("-", "_")] = secret.value
                logger.info("Loaded secrets from Azure Key Vault: %s", kv_name)
                _initialized = True
                return
            except Exception as exc:
                logger.warning("Key Vault load failed (%s); falling back to .env", exc)

        load_dotenv(override=False)
        _initialized = True
