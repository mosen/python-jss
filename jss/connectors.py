import re
from xml.etree import ElementTree

import requests

from jss import JSSGetError, JSSDeleteError, JSSPutError, JSSPostError
from jss.jamf_software_server import JSSObjectFactory
from jss.tlsadapter import TLSAdapter
from jss.tools import error_handler
from . import distribution_points
from urllib import quote
import json


class JSSUAPIConnector(JSSConnector):
    """Represents a connection to the JSON/UAPI endpoint on a Jamf Pro Server.

    This object handles transport specifics for the API and the API's required authentication method(s).
    """
    def __init__(self, *args, **kwargs):
        super(JSSUAPIConnector, self).__init__(*args, **kwargs)
        if self.suppress_warnings:
            requests.packages.urllib3.disable_warnings()

        self.session = requests.Session()

        # Add a TransportAdapter to force TLS, since JSS no longer
        # accepts SSLv23, which is the default.

        self.session.mount(self.base_url, TLSAdapter())


    @property
    def _url(self):
        """The URL to the Casper JSS UAPI endpoints. Get only."""
        return "%s/%s" % (self.base_url, "uapi")

    def _init_jsessionid(self):
        """Get the index page to retrieve a JSESSIONID."""
        pass

    def _create_token(self):
        self.session.post("%s%s" % (self._url, '/auth/tokens'), )


class JSSScraperConnector(JSSConnector):
    """Represents a connection to the JAMF Pro UI via form post/scraping."""

    def __init__(self, *args, **kwargs):
        super(JSSScraperConnector, self).__init__(*args, **kwargs)
        if self.suppress_warnings:
            requests.packages.urllib3.disable_warnings()

        self.session = requests.Session()

        # Add a TransportAdapter to force TLS, since JSS no longer
        # accepts SSLv23, which is the default.

        self.session.mount(self.base_url, TLSAdapter())

    def _login(self):
        response = self.session.post(self._base_url, data={'username': self.user, 'password': self.password})
        # JSESSIONID cookie will be stored for subsequent requests


