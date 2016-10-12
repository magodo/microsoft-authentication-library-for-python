"""This OAuth2 client implementation aims to be spec-compliant, and generic."""
# OAuth2 spec https://tools.ietf.org/html/rfc6749

try:
    from urllib.parse import urlencode, parse_qs
except ImportError:
    from urlparse import parse_qs
    from urllib import urlencode

import requests


class Client(object):
    # This low-level interface works. Yet you'll find those *Grant sub-classes
    # more friendly to remind you what parameters are needed in each scenario.
    # More on Client Types at https://tools.ietf.org/html/rfc6749#section-2.1
    def __init__(
            self, client_id,
            client_secret=None,  # Triggers HTTP AUTH for Confidential Client
            default_body=None,  # a dict to be sent in each token request,
                # usually contains Confidential Client authentication parameters
                # such as {'client_id': 'your_id', 'client_secret': 'secret'}
                # if you choose to not use HTTP AUTH
            authorization_endpoint=None, token_endpoint=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.default_body = default_body or {}
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint

    def _authorization_url(self, response_type, **kwargs):
        # response_type can be set to "code" or "token".
        params = {'client_id': self.client_id, 'response_type': response_type}
        params.update(kwargs)  # Note: None values will override params
        params = {k: v for k, v in params.items() if v is not None}  # clean up
        if params.get('scope'):
            params['scope'] = self._normalize_to_string(params['scope'])
        sep = '&' if '?' in self.authorization_endpoint else '?'
        return "%s%s%s" % (self.authorization_endpoint, sep, urlencode(params))

    def _get_token(
            self, grant_type,
            query=None,  # a dict to be send as query string to the endpoint
            **kwargs  # All relevant parameters, which will go into the body
            ):
        data = {'client_id': self.client_id, 'grant_type': grant_type}
        data.update(self.default_body)  # It may contain authen parameters
        data.update(  # Here we use None to mean "use default value instead"
            {k: v for k, v in kwargs.items() if v is not None})
        # We don't have to clean up None values here, because requests lib will.

        if data.get('scope'):
            data['scope'] = self._normalize_to_string(data['scope'])

        # Quoted from https://tools.ietf.org/html/rfc6749#section-2.3.1
        # Clients in possession of a client password MAY use the HTTP Basic
        # authentication.
        # Alternatively, (but NOT RECOMMENDED,)
        # the authorization server MAY support including the
        # client credentials in the request-body using the following
        # parameters: client_id, client_secret.
        auth = None
        if self.client_secret and self.client_id:
            auth = (self.client_id, self.client_secret)  # for HTTP Basic Auth

        assert self.token_endpoint, "You need to provide token_endpoint"
        resp = requests.post(
            self.token_endpoint, headers={'Accept': 'application/json'},
            params=query, data=data, auth=auth)
        if resp.status_code>=500:
            resp.raise_for_status()  # TODO: Will probably retry here
        # The spec (https://tools.ietf.org/html/rfc6749#section-5.2) says
        # even an error response will be a valid json structure,
        # so we simply return it here, without needing to invent an exception.
        return resp.json()

    def get_token_by_refresh_token(self, refresh_token, scope=None, **kwargs):
        return self._get_token(
            "refresh_token", refresh_token=refresh_token, scope=scope, **kwargs)

    def _normalize_to_string(self, scope):
        if isinstance(scope, (list, set, tuple)):
            return ' '.join(scope)
        return scope  # as-is


class AuthorizationCodeGrant(Client):
    # Can be used by Confidential Client or Public Client.
    # See https://tools.ietf.org/html/rfc6749#section-4.1.3

    def authorization_url(
            self, redirect_uri=None, scope=None, state=None, **kwargs):
        """Generate an authorization url to be visited by resource owner.

        :param redirect_uri: Optional. Server will use the pre-registered one.
        :param scope: It is a space-delimited, case-sensitive string.
            Some ID provider can accept empty string to represent default scope.
        """
        return super(AuthorizationCodeGrant, self)._authorization_url(
            'code', redirect_uri=redirect_uri, scope=scope, state=state,
            **kwargs)
        # Later when you receive the response at your redirect_uri,
        # validate_authorization() may be handy to check the returned state.

    def get_token(self, code, redirect_uri=None, **kwargs):
        """Get an access token.

        See also https://tools.ietf.org/html/rfc6749#section-4.1.3

        :param code: The authorization code received from authorization server.
        :param redirect_uri:
            Required, if the "redirect_uri" parameter was included in the
            authorization request, and their values MUST be identical.
        :param client_id: Required, if the client is not authenticating itself.
            See https://tools.ietf.org/html/rfc6749#section-3.2.1
        """
        return super(AuthorizationCodeGrant, self)._get_token(
            'authorization_code', code=code,
            redirect_uri=redirect_uri, **kwargs)


def validate_authorization(params, state=None):
    """A thin helper to examine the authorization being redirected back"""
    if not isinstance(params, dict):
        params = parse_qs(params)
    if params.get('state') != state:
        raise ValueError('state mismatch')
    return params


class ImplicitGrant(Client):
    """Implicit Grant is used to obtain access tokens (but not refresh token).

    It is optimized for public clients known to operate a particular
    redirection URI.  These clients are typically implemented in a browser
    using a scripting language such as JavaScript.
    Quoted from https://tools.ietf.org/html/rfc6749#section-4.2
    """
    def authorization_url(self, redirect_uri=None, scope=None, state=None):
        return super(ImplicitGrant, self)._authorization_url(
            'token', **locals())


class ResourceOwnerPasswordCredentialsGrant(Client):  # Legacy Application flow
    def get_token(self, username, password, scope=None, **kwargs):
        return super(ResourceOwnerPasswordCredentialsGrant, self)._get_token(
            "password", username=username, password=password, scope=scope,
            **kwargs)


class ClientCredentialGrant(Client):  # a.k.a. Backend Application flow
    def get_token(self, scope=None, **kwargs):
        '''Get token by client credential.

        You may want to also provide an optional client_secret parameter,
        or you can provide such extra parameters as `default_body` during the
        class initialization.
        '''
        return super(ClientCredentialGrant, self)._get_token(
            "client_credentials", scope=scope, **kwargs)

