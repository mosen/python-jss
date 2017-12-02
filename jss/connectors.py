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


class JSSConnector(object):
    """Represents a JAMF Software Server, with object search methods.

    Attributes:
        base_url: String, full URL to the JSS, with port.
        user: String API username.
        password: String API password for user.
        repo_prefs: List of dicts of repository configuration data.
        verbose: Boolean whether to include extra output.
        jss_migrated: Boolean whether JSS has had scripts "migrated".
            Used to determine whether to upload scripts in Script
            object XML or as files to the distribution points.
        session: Requests session used to make all HTTP requests.
        ssl_verify: Boolean whether to verify SSL traffic from the JSS
            is genuine.
        factory: JSSObjectFactory object for building JSSObjects.
        distribution_points: DistributionPoints
    """

    # pylint: disable=too-many-arguments
    def __init__(self, jss_prefs=None, url=None, user=None, password=None,
                 repo_prefs=None, ssl_verify=True, verbose=False,
                 jss_migrated=False, suppress_warnings=False):
        """Setup a JSS for making API requests.

        Provide either a JSSPrefs object OR specify url, user, and
        password to init. Other parameters are optional.

        Args:
            jss_prefs:  A JSSPrefs object.
            url: String, full URL to a JSS, with port.
            user: API Username.
            password: API Password.

            repo_prefs: A list of dicts with repository names and
                passwords.
            repos: (Optional) List of file repositories dicts to
                    connect.
                repo dicts:
                    Each file-share distribution point requires:
                        name: String name of the distribution point.
                            Must match the value on the JSS.
                        password: String password for the read/write
                            user.

                    This form uses the distributionpoints API call to
                    determine the remaining information. There is also
                    an explicit form; See distribution_points package
                    for more info

                    CDP and JDS types require one dict for the master,
                    with key:
                        type: String, either "CDP" or "JDS".

            ssl_verify: Boolean whether to verify SSL traffic from the
                JSS is genuine.
            verbose: Boolean whether to include extra output.
            jss_migrated: Boolean whether JSS has had scripts
                "migrated". Used to determine whether to upload scripts
                in Script object XML or as files to the distribution
                points.
            suppress_warnings: Turns off the urllib3 warnings. Remember,
                these warnings are there for a reason! Use at your own
                risk.
        """
        if jss_prefs is not None:
            url = jss_prefs.url
            user = jss_prefs.user
            password = jss_prefs.password
            repo_prefs = jss_prefs.repos
            ssl_verify = jss_prefs.verify
            suppress_warnings = jss_prefs.suppress_warnings

        self._base_url = ""
        self.base_url = url
        self.user = user
        self.password = password
        self.repo_prefs = repo_prefs if repo_prefs else []
        self.verbose = verbose
        self.jss_migrated = jss_migrated
        self.ssl_verify = ssl_verify
        self.suppress_warnings = suppress_warnings

    @property
    def base_url(self):
        """The URL to the Casper JSS, including port if needed."""
        return self._base_url

    @base_url.setter
    def base_url(self, url):
        """The URL to the Casper JSS, including port if needed."""
        # Remove the frequently included yet incorrect trailing slash.
        self._base_url = url.rstrip("/")


class JSSAPIConnector(JSSConnector):
    """Represents a connection to the XML/Legacy API endpoint on a Jamf Pro Server.

    This object handles transport specifics for the API and the API's required authentication method(s).
    """

    def __init__(self, *args, **kwargs):
        super(JSSAPIConnector, self).__init__(*args, **kwargs)
        if self.suppress_warnings:
            requests.packages.urllib3.disable_warnings()

        self.session = requests.Session()
        self.session.auth = (self.user, self.password)
        
        # For some objects the JSS tries to return JSON, so we explictly
        # request XML.

        headers = {"content-type": "text/xml", "Accept": "application/xml"}
        self.session.headers.update(headers)

        # Add a TransportAdapter to force TLS, since JSS no longer
        # accepts SSLv23, which is the default.

        self.session.mount(self.base_url, TLSAdapter())
        
        self.factory = JSSObjectFactory(self)
        self.distribution_points = distribution_points.DistributionPoints(self)

    @property
    def _url(self):
        """The URL to the Casper JSS API endpoints. Get only."""
        return "%s/%s" % (self.base_url, "JSSResource")

    @property
    def ssl_verify(self):
        """Boolean value for whether to verify SSL traffic is valid."""
        return self.session.verify

    @ssl_verify.setter
    def ssl_verify(self, value):
        """Boolean value for whether to verify SSL traffic is valid.

        Args:
            value: Boolean.
        """
        self.session.verify = value

    def get(self, url_path):
        """GET a url, handle errors, and return an etree.

        In general, it is better to use a higher level interface for
        API requests, like the search methods on this class, or the
        JSSObjects themselves.

        Args:
            url_path: String API endpoint path to GET (e.g. "/packages")

        Returns:
            ElementTree.Element for the XML returned from the JSS.

        Raises:
            JSSGetError if provided url_path has a >= 400 response, for
            example, if an object queried for does not exist (404). Will
            also raise JSSGetError for bad XML.

            This behavior will change in the future for 404/Not Found
            to returning None.
        """
        request_url = "%s%s" % (self._url, quote(url_path.encode("utf_8")))
        response = self.session.get(request_url)

        if response.status_code == 200 and self.verbose:
            print "GET %s: Success." % request_url
        elif response.status_code >= 400:
            error_handler(JSSGetError, response)

        # requests GETs JSS data as XML encoded in utf-8, but
        # ElementTree.fromstring wants a string.
        jss_results = response.text.encode("utf-8")
        try:
            xmldata = ElementTree.fromstring(jss_results)
        except ElementTree.ParseError:
            raise JSSGetError("Error Parsing XML:\n%s" % jss_results)

        return xmldata

    def post(self, obj_class, url_path, data, serialize='xml'):
        """POST an object to the JSS. For creating new objects only.

        The data argument is POSTed to the JSS, which, upon success,
        returns the complete XML for the new object. This data is used
        to get the ID of the new object, and, via the
        JSSObjectFactory, GET that ID to instantiate a new JSSObject of
        class obj_class.

        This allows incomplete (but valid) XML for an object to be used
        to create a new object, with the JSS filling in the remaining
        data. Also, only the JSS may specify things like ID, so this
        method retrieves those pieces of data.

        In general, it is better to use a higher level interface for
        creating new objects, namely, creating a JSSObject subclass and
        then using its save method.

        Args:
            obj_class: JSSObject subclass to create from POST.
            url_path: String API endpoint path to POST (e.g.
                "/packages/id/0")
            data: xml.etree.ElementTree.Element with valid XML for the
                desired obj_class.

        Returns:
            An object of class obj_class, representing a newly created
            object on the JSS. The data is what has been returned after
            it has been parsed by the JSS and added to the database.

        Raises:
            JSSPostError if provided url_path has a >= 400 response.
        """
        # The JSS expects a post to ID 0 to create an object

        request_url = "%s%s" % (self._url, url_path)

        data = ElementTree.tostring(data)
        response = self.session.post(request_url, data=data)

        if response.status_code == 201 and self.verbose:
            print "POST %s: Success" % request_url
        elif response.status_code >= 400:
            error_handler(JSSPostError, response)

        # Get the ID of the new object. JSS returns xml encoded in utf-8

        jss_results = response.text.encode("utf-8")
        id_ = int(re.search(r"<id>([0-9]+)</id>", jss_results).group(1))

        return self.factory.get_object(obj_class, id_)

    def put(self, url_path, data):
        """Update an existing object on the JSS.

        In general, it is better to use a higher level interface for
        updating objects, namely, making changes to a JSSObject subclass
        and then using its save method.

        Args:
            url_path: String API endpoint path to PUT, with ID (e.g.
                "/packages/id/<object ID>")
            data: xml.etree.ElementTree.Element with valid XML for the
                desired obj_class.
        Raises:
            JSSPutError if provided url_path has a >= 400 response.
        """
        request_url = "%s%s" % (self._url, url_path)
        data = ElementTree.tostring(data)
        response = self.session.put(request_url, data)

        if response.status_code == 201 and self.verbose:
            print "PUT %s: Success." % request_url
        elif response.status_code >= 400:
            error_handler(JSSPutError, response)

    def delete(self, url_path, data=None):
        """Delete an object from the JSS.

        In general, it is better to use a higher level interface for
        deleting objects, namely, using a JSSObject's delete method.

        Args:
            url_path: String API endpoint path to DEL, with ID (e.g.
                "/packages/id/<object ID>")

        Raises:
            JSSDeleteError if provided url_path has a >= 400 response.
        """
        request_url = "%s%s" % (self._url, url_path)
        if data:
            response = self.session.delete(request_url, data=data)
        else:
            response = self.session.delete(request_url)

        if response.status_code == 200 and self.verbose:
            print "DEL %s: Success." % request_url
        elif response.status_code >= 400:
            error_handler(JSSDeleteError, response)


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


