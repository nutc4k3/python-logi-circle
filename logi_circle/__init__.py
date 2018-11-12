"""Python wrapper for the official Logi Circle API"""
# coding: utf-8
# vim:sw=4:ts=4:et:
import logging

from .const import DEFAULT_SCOPES, DEFAULT_CACHE_FILE, API_BASE, ACCESSORIES_ENDPOINT
from .auth import AuthProvider
from .camera import Camera
from .exception import NotAuthorized, AuthorizationFailed

_LOGGER = logging.getLogger(__name__)


class LogiCircle():
    """A Python abstraction object to Logi Circle cameras."""

    def __init__(self,
                 client_id,
                 client_secret,
                 redirect_uri,
                 api_key,
                 scopes=DEFAULT_SCOPES,
                 cache_file=DEFAULT_CACHE_FILE):
        self.auth_provider = AuthProvider(client_id=client_id,
                                          client_secret=client_secret,
                                          redirect_uri=redirect_uri,
                                          scopes=scopes,
                                          cache_file=cache_file,
                                          logi_base=self)
        self.authorize = self.auth_provider.authorize
        self.api_key = api_key
        self.is_connected = False

    @property
    def authorized(self):
        """Checks if the current client ID has a refresh token"""
        return self.auth_provider.authorized

    @property
    def authorize_url(self):
        """Returns the authorization URL for the Logi Circle API"""
        return self.auth_provider.authorize_url

    async def close(self):
        """Closes the aiohttp session"""
        await self.auth_provider.close()

    @property
    async def cameras(self):
        """Return all cameras."""
        cameras = []
        raw_cameras = await self._fetch(ACCESSORIES_ENDPOINT)

        for camera in raw_cameras:
            cameras.append(Camera(self, camera))

        return cameras

    async def _fetch(self,
                     url,
                     method='GET',
                     params=None,
                     request_body=None,
                     relative_to_api_root=True,
                     raw=False,
                     _reattempt=False):
        """Query data from the Logi Circle API."""

        if not self.auth_provider.authorized:
            raise NotAuthorized('No access token available for this client ID')

        headers = {
            'X-API-Key': self.api_key,
            'Authorization': 'Bearer %s' % (self.auth_provider.access_token)
        }

        resolved_url = (API_BASE + url if relative_to_api_root else url)
        _LOGGER.debug("Fetching %s (%s)", resolved_url, method)

        resp = None
        session = await self.auth_provider.get_session()

        # Perform request
        if method == 'GET':
            resp = await session.get(resolved_url, headers=headers, params=params)
        elif method == 'POST':
            resp = await session.post(resolved_url, headers=headers, params=params, json=request_body)
        elif method == 'PUT':
            resp = await session.put(resolved_url, headers=headers, params=params, json=request_body)
        else:
            raise ValueError('Method %s not supported.' % (method))

        _LOGGER.debug('Request %s (%s) returned %s',
                      resolved_url, method, resp.status)

        if resp.status == 401 and not _reattempt:
            # Token may have expired. Refresh and try again.
            await self.auth_provider.refresh()
            return await self._fetch(
                url=url,
                method=method,
                params=params,
                request_body=request_body,
                relative_to_api_root=relative_to_api_root,
                raw=raw,
                _reattempt=True
            )
        if resp.status == 401 and _reattempt:
            raise AuthorizationFailed('Could not refresh access token')

        if raw:
            return resp
        resp_data = await resp.json()
        resp.close()
        return resp_data
