# -*- coding: utf-8 -*-

# Copyright 2015 Spanish National Research Council
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy
import json

from ooi import utils

from oslo_log import log as logging
import webob.exc

LOG = logging.getLogger(__name__)


def exception_from_response(response):
    """Convert an OpenStack V2 Fault into a webob exception.

    Since we are calling the OpenStack API we should process the Faults
    produced by them. Extract the Fault information according to [1] and
    convert it back to a webob exception.

    [1] http://docs.openstack.org/developer/nova/v2/faults.html

    :param response: a webob.Response containing an exception
    :returns: a webob.exc.exception object
    """
    exceptions = {
        400: webob.exc.HTTPBadRequest,
        401: webob.exc.HTTPUnauthorized,
        403: webob.exc.HTTPForbidden,
        404: webob.exc.HTTPNotFound,
        405: webob.exc.HTTPMethodNotAllowed,
        406: webob.exc.HTTPNotAcceptable,
        409: webob.exc.HTTPConflict,
        413: webob.exc.HTTPRequestEntityTooLarge,
        415: webob.exc.HTTPUnsupportedMediaType,
        429: webob.exc.HTTPTooManyRequests,
        501: webob.exc.HTTPNotImplemented,
        503: webob.exc.HTTPServiceUnavailable,
    }
    code = response.status_int
    try:
        message = response.json_body.popitem()[1].get("message")
    except Exception:
        LOG.exception("Unknown error happenened processing response %s"
                      % response)
        return webob.exc.HTTPInternalServerError

    exc = exceptions.get(code, webob.exc.HTTPInternalServerError)
    return exc(explanation=message)


class BaseHelper(object):
    """Base helper to interact with nova API."""
    def __init__(self, app, openstack_version):
        self.app = app
        self.openstack_version = openstack_version

    def _get_req(self, req, method,
                 path=None,
                 content_type="application/json",
                 body=None,
                 query_string=""):
        """Return a new Request object to interact with OpenStack.

        This method will create a new request starting with the same WSGI
        environment as the original request, prepared to interact with
        OpenStack. Namely, it will override the script name to match the
        OpenStack version. It will also override the path, content_type and
        body of the request, if any of those keyword arguments are passed.

        :param req: the original request
        :param path: new path for the request
        :param content_type: new content type for the request, defaults to
                             "application/json" if not specified
        :param body: new body for the request
        :param query_string: query string for the request, defaults to an empty
                             query if not specified
        :returns: a Request object
        """
        new_req = webob.Request(copy.copy(req.environ))
        new_req.script_name = self.openstack_version
        new_req.query_string = query_string
        new_req.method = method
        if path is not None:
            new_req.path_info = path
        if content_type is not None:
            new_req.content_type = content_type
        if body is not None:
            new_req.body = utils.utf8(body)
        return new_req

    @staticmethod
    def get_from_response(response, element, default):
        """Get a JSON element from a valid response or raise an exception.

        This method will extract an element a JSON response (falling back to a
        default value) if the response has a code of 200, otherwise it will
        raise a webob.exc.exception

        :param response: The webob.Response object
        :param element: The element to look for in the JSON body
        :param default: The default element to be returned if not found.
        """
        if response.status_int in [200, 201, 202]:
            return response.json_body.get(element, default)
        else:
            raise exception_from_response(response)


class OpenStackHelper(BaseHelper):
    """Class to interact with the nova API."""

    @staticmethod
    def tenant_from_req(req):
        return req.environ["keystone.token_auth"].user.project_id

    def _get_index_req(self, req):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/servers" % tenant_id
        return self._get_req(req, path=path, method="GET")

    def index(self, req):
        """Get a list of servers for a tenant.

        :param req: the incoming request
        """
        os_req = self._get_index_req(req)
        response = os_req.get_response(self.app)
        return self.get_from_response(response, "servers", [])

    def _get_delete_req(self, req, server_id):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/servers/%s" % (tenant_id, server_id)
        return self._get_req(req, path=path, method="DELETE")

    def delete(self, req, server_id):
        """Delete a server.

        :param req: the incoming request
        :param server_id: server id to delete
        """
        os_req = self._get_delete_req(req, server_id)
        response = os_req.get_response(self.app)
        # FIXME(aloga): this should be handled in get_from_response, shouldn't
        # it?
        if response.status_int not in [204]:
            raise exception_from_response(response)

    def _get_run_action_req(self, req, action, server_id):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/servers/%s/action" % (tenant_id, server_id)

        actions_map = {
            "stop": {"os-stop": None},
            "start": {"os-start": None},
            "restart": {"reboot": {"type": "SOFT"}},
        }
        action = actions_map[action]

        body = json.dumps(action)
        return self._get_req(req, path=path, body=body, method="POST")

    def run_action(self, req, action, server_id):
        """Run an action on a server.

        :param req: the incoming request
        :param action: the action to run
        :param server_id: server id to delete
        """
        os_req = self._get_run_action_req(req, action, server_id)
        response = os_req.get_response(self.app)
        if response.status_int != 202:
            raise exception_from_response(response)

    def _get_server_req(self, req, server_id):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/servers/%s" % (tenant_id, server_id)
        return self._get_req(req, path=path, method="GET")

    def get_server(self, req, server_id):
        """Get info from a server.

        :param req: the incoming request
        :param server_id: server id to get info from
        """
        req = self._get_server_req(req, server_id)
        response = req.get_response(self.app)
        return self.get_from_response(response, "server", {})

    def _get_create_server_req(self, req, name, image, flavor, user_data=None):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/servers" % tenant_id
        # TODO(enolfc): add here the correct metadata info
        # if contextualization.public_key.scheme in obj["schemes"]:
        #     req_body["metadata"] = XXX
        body = {"server": {
            "name": name,
            "imageRef": image,
            "flavorRef": flavor,
        }}
        if user_data is not None:
            body["server"]["user_data"] = user_data
        return self._get_req(req,
                             path=path,
                             content_type="application/json",
                             body=json.dumps(body),
                             method="POST")

    def create_server(self, req, name, image, flavor, user_data=None):
        """Create a server.

        :param req: the incoming request
        :param name: name for the new server
        :param image: image id for the new server
        :param flavor: flavor id for the new server
        :param user_data: user data to inject into the server
        """
        req = self._get_create_server_req(req, name, image, flavor,
                                          user_data=None)
        response = req.get_response(self.app)
        # We only get one server
        return self.get_from_response(response, "server", {})

    def _get_flavor_req(self, req, flavor_id):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/flavors/%s" % (tenant_id, flavor_id)
        return self._get_req(req, path=path, method="GET")

    def get_flavor(self, req, flavor_id):
        """Get information from a flavor.

        :param req: the incoming request
        :param flavor_id: flavor id to get info from
        """
        req = self._get_flavor_req(req, flavor_id)
        response = req.get_response(self.app)
        return self.get_from_response(response, "flavor", {})

    def _get_image_req(self, req, image_id):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/images/%s" % (tenant_id, image_id)
        return self._get_req(req, path=path, method="GET")

    def get_image(self, req, image_id):
        """Get information from an image.

        :param req: the incoming request
        :param image_id: image id to get info from
        """
        req = self._get_image_req(req, image_id)
        response = req.get_response(self.app)
        return self.get_from_response(response, "image", {})

    def _get_volumes_req(self, req, server_id):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/servers/%s/os-volume_attachments" % (tenant_id, server_id)
        return self._get_req(req, path=path, method="GET")

    def get_volumes(self, req, server_id):
        """Get volumes attached to a server.

        :param req: the incoming request
        :param server_id: server id to get volumes from
        """
        req = self._get_volumes_req(req, server_id)
        response = req.get_response(self.app)
        return self.get_from_response(response, "volumeAttachments", [])

    def _get_floating_ips(self, req):
        tenant_id = self.tenant_from_req(req)
        path = "/%s/os-floating-ips" % tenant_id
        return self._get_req(req, path=path, method="GET")

    def get_floating_ips(self, req):
        """Get floating IPs for the tenant.

        :param req: the incoming request
        """
        req = self._get_floating_ips(req)
        response = req.get_response(self.app)
        return self.get_from_response(response, "floating_ips", [])