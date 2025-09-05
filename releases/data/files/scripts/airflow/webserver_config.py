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

PROVIDER_NAME = "dex"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AIRFLOW__API__BASE_URL = os.getenv("AIRFLOW__API__BASE_URL")
OIDC_ISSUER = os.getenv("OIDC_ISSUER")
OIDC_BASE_URL = f"{OIDC_ISSUER}/protocol/openid-connect"
OIDC_TOKEN_URL = f"{OIDC_BASE_URL}/token"
OIDC_AUTH_URL = f"{OIDC_BASE_URL}/auth"
OIDC_METADATA_URL = f"{OIDC_ISSUER}/.well-known/openid-configuration"
OAUTH_PROVIDERS = [
    {
        "name": PROVIDER_NAME,
        "token_key": "access_token",
        "icon": "fa-key",
        "remote_app": {
            "api_base_url": OIDC_BASE_URL,
            "access_token_url": OIDC_TOKEN_URL,
            "authorize_url": OIDC_AUTH_URL,
            "server_metadata_url": OIDC_METADATA_URL,
            "request_token_url": None,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "client_kwargs": {
                "scope": "email profile",
                "code_challenge_method": "S256",
                "response_type": "code",
            },
        },
    }
]

# Fetch public key
req = requests.get(OIDC_ISSUER)
key_der_base64 = req.json()["public_key"]
key_der = b64decode(key_der_base64.encode())
public_key = serialization.load_der_public_key(key_der)


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
