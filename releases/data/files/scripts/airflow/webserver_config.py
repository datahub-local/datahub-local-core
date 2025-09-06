from airflow.providers.fab.auth_manager.security_manager.override import (
    FabAirflowSecurityManagerOverride,
)
from base64 import b64decode
from cryptography.hazmat.primitives import serialization
from flask import redirect, session
from flask_appbuilder import expose
from flask_appbuilder.security.manager import AUTH_OAUTH
from flask_appbuilder.security.views import AuthOAuthView
import jwt
import logging
import os
import requests

log = logging.getLogger(__name__)
CSRF_ENABLED = True
AUTH_TYPE = AUTH_OAUTH
AUTH_USER_REGISTRATION = True
AUTH_ROLES_SYNC_AT_LOGIN = True
AUTH_USER_REGISTRATION_ROLE = "Admin"
PERMANENT_SESSION_LIFETIME = 43200

PROVIDER_NAME = "IAM"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

AIRFLOW__API__BASE_URL = os.getenv("AIRFLOW__API__BASE_URL")

OIDC_ISSUER = os.getenv("OIDC_ISSUER")
OIDC_METADATA_URL = f"{OIDC_ISSUER}/.well-known/openid-configuration"


# Fetch metadata
req = requests.get(OIDC_METADATA_URL)
metadata = req.json()

OIDC_KEYS_URL = metadata["jwks_uri"]
OIDC_AUTH_URL = metadata["authorization_endpoint"]
OIDC_TOKEN_URL = metadata["token_endpoint"]
OAUTH_PROVIDERS = [
    {
        "name": PROVIDER_NAME,
        "token_key": "access_token",
        "icon": "fa-key",
        "remote_app": {
            "api_base_url": OIDC_ISSUER,
            "access_token_url": OIDC_TOKEN_URL,
            "authorize_url": OIDC_AUTH_URL,
            "server_metadata_url": OIDC_METADATA_URL,
            "request_token_url": None,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "client_kwargs": {
                "scope": "email openid profile",
                "code_challenge_method": "S256",
                "response_type": "code",
            },
        },
    }
]

# Fetch public keys
req = requests.get(OIDC_KEYS_URL)
jwks = req.json()


class CustomOAuthView(AuthOAuthView):
    @expose("/logout/", methods=["GET", "POST"])
    def logout(self):
        session.clear()
        return redirect(
            f"{OIDC_ISSUER}/protocol/openid-connect/logout?post_logout_redirect_uri={AIRFLOW__API__BASE_URL}&client_id={CLIENT_ID}"
        )


class CustomSecurityManager(FabAirflowSecurityManagerOverride):
    authoauthview = CustomOAuthView

    def get_oauth_user_info(self, provider, response):
        if provider == PROVIDER_NAME:
            id_token = response["id_token"]

            unverified_header = jwt.get_unverified_header(id_token)
            kid = unverified_header["kid"]
            public_key = None
            for k in jwks["keys"]:
                if k["kid"] == kid:
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                    break

            token = response["access_token"]
            me = jwt.decode(
                token, public_key, algorithms=["HS256", "RS256"], audience=CLIENT_ID
            )

            userinfo = {
                "username": me.get("preferred_username"),
                "email": me.get("email"),
                "first_name": me.get("given_name"),
                "last_name": me.get("family_name"),
            }

            log.info(f"user info: {userinfo}")

            return userinfo
        else:
            return {}


# Make sure to replace this with your own implementation of AirflowSecurityManager class
SECURITY_MANAGER_CLASS = CustomSecurityManager
