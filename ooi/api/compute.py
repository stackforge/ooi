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

import ooi.api.base
import ooi.api.helpers
import ooi.api.network as network_api
from ooi import exception
from ooi.occi.core import collection
from ooi.occi.infrastructure import compute
from ooi.occi.infrastructure import network
from ooi.occi.infrastructure import storage
from ooi.occi.infrastructure import storage_link
from ooi.occi import validator as occi_validator
from ooi.openstack import contextualization
from ooi.openstack import helpers
from ooi.openstack import network as os_network
from ooi.openstack import templates


def _create_network_link(addr, comp, floating_ips):
    if addr["OS-EXT-IPS:type"] == "floating":
        for ip in floating_ips:
            if addr["addr"] == ip["ip"]:
                net = network.NetworkResource(
                    title="network",
                    id="%s/%s" % (network_api.FLOATING_PREFIX, ip["pool"]))
    else:
        net = network.NetworkResource(title="network", id="fixed")
    return os_network.OSNetworkInterface(comp, net,
                                         addr["OS-EXT-IPS-MAC:mac_addr"],
                                         addr["addr"])


class Controller(ooi.api.base.Controller):
    def __init__(self, *args, **kwargs):
        super(Controller, self).__init__(*args, **kwargs)
        self.compute_actions = compute.ComputeResource.actions
        self.os_helper = ooi.api.helpers.OpenStackHelper(
            self.app,
            self.openstack_version
        )

    def _get_compute_resources(self, servers):
        occi_compute_resources = []
        if servers:
            for s in servers:
                s = compute.ComputeResource(title=s["name"], id=s["id"])
                occi_compute_resources.append(s)

        return occi_compute_resources

    def index(self, req):
        servers = self.os_helper.index(req)
        occi_compute_resources = self._get_compute_resources(servers)

        return collection.Collection(resources=occi_compute_resources)

    def run_action(self, req, id, body):
        action = req.GET.get("action", None)
        occi_actions = [a.term for a in compute.ComputeResource.actions]

        if action is None or action not in occi_actions:
            raise exception.InvalidAction(action=action)

        parser = req.get_parser()(req.headers, req.body)
        obj = parser.parse()

        if action == "stop":
            scheme = {"category": compute.stop}
        elif action == "start":
            scheme = {"category": compute.start}
        elif action == "restart":
            scheme = {"category": compute.restart}
        else:
            raise exception.NotImplemented

        validator = occi_validator.Validator(obj)
        validator.validate(scheme)

        self.os_helper.run_action(req, action, id)
        return []

    def create(self, req, body):
        parser = req.get_parser()(req.headers, req.body)
        scheme = {
            "category": compute.ComputeResource.kind,
            "mixins": [
                templates.OpenStackOSTemplate,
                templates.OpenStackResourceTemplate,
            ],
            "optional_mixins": [
                contextualization.user_data,
                contextualization.public_key,
            ]
        }
        obj = parser.parse()
        validator = occi_validator.Validator(obj)
        validator.validate(scheme)

        attrs = obj.get("attributes", {})
        name = attrs.get("occi.core.title", "OCCI VM")
        image = obj["schemes"][templates.OpenStackOSTemplate.scheme][0]
        flavor = obj["schemes"][templates.OpenStackResourceTemplate.scheme][0]
        user_data = None
        if contextualization.user_data.scheme in obj["schemes"]:
            user_data = attrs.get("org.openstack.compute.user_data")

        server = self.os_helper.create_server(req, name, image, flavor,
                                              user_data=user_data)
        # The returned JSON does not contain the server name
        server["name"] = name
        occi_compute_resources = self._get_compute_resources([server])

        return collection.Collection(resources=occi_compute_resources)

    def show(self, req, id):
        # get info from server
        s = self.os_helper.get_server(req, id)

        # get info from flavor
        flavor = self.os_helper.get_flavor(req, s["flavor"]["id"])
        res_tpl = templates.OpenStackResourceTemplate(flavor["id"],
                                                      flavor["name"],
                                                      flavor["vcpus"],
                                                      flavor["ram"],
                                                      flavor["disk"])

        # get info from image
        image = self.os_helper.get_image(req, s["image"]["id"])
        os_tpl = templates.OpenStackOSTemplate(image["id"],
                                               image["name"])

        # build the compute object
        comp = compute.ComputeResource(title=s["name"], id=s["id"],
                                       cores=flavor["vcpus"],
                                       hostname=s["name"],
                                       memory=flavor["ram"],
                                       state=helpers.vm_state(s["status"]),
                                       mixins=[os_tpl, res_tpl])

        # storage links
        vols = self.os_helper.get_server_volumes_link(req, s["id"])
        for v in vols:
            st = storage.StorageResource(title="storage", id=v["volumeId"])
            comp.add_link(storage_link.StorageLink(comp, st,
                                                   deviceid=v["device"]))

        # network links
        addresses = s.get("addresses", {})
        if addresses:
            floating_ips = self.os_helper.get_floating_ips(req)
            for addr_set in addresses.values():
                for addr in addr_set:
                    comp.add_link(_create_network_link(addr, comp,
                                                       floating_ips))

        return [comp]

    def _delete(self, req, server_ids):
        for server_id in server_ids:
            self.os_helper.delete(req, server_id)
        return []

    def delete(self, req, id):
        return self._delete(req, [id])

    def delete_all(self, req):
        ids = [s["id"] for s in self.os_helper.index(req)]
        return self._delete(req, ids)
