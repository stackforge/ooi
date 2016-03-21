# -*- coding: utf-8 -*-

# Copyright 2016 Spanish National Research Council
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

# import mock
import webob.exc

from ooi.occi.core import action
from ooi.occi.core import attribute
# from ooi.occi.core import collection
from ooi.occi.core import kind
# from ooi.occi.core import link
from ooi.occi.core import mixin
from ooi.occi.core import resource
# from ooi.occi.infrastructure import action
# from ooi.occi.infrastructure import compute
# from ooi.occi.infrastructure import network
# from ooi.occi.infrastructure import network_link
# from ooi.occi.infrastructure import storage
# from ooi.occi.infrastructure import storage_link
# from ooi.occi.infrastructure import templatesa
import ooi.tests.base


class BaseRendererTest(ooi.tests.base.TestCase):
    def get_render_and_assert(self, obj, observed=None):
        if observed is None:
            r = self.renderer.get_renderer(obj)
            observed = r.render()

        if isinstance(obj, action.Action):
            self.assertAction(obj, observed)
        elif isinstance(obj, kind.Kind):
            self.assertKind(obj, observed)
        elif isinstance(obj, resource.Resource):
            self.assertResource(obj, observed)
        elif isinstance(obj, webob.exc.HTTPException):
            self.assertException(obj, observed)

    def test_exception(self):
        exc = webob.exc.HTTPBadRequest("foo")
        self.get_render_and_assert(exc)

    def test_action(self):
        act = action.Action("scheme", "term", "title")
        self.get_render_and_assert(act)

    def test_kind(self):
        knd = kind.Kind("scheme", "term", "title")
        self.get_render_and_assert(knd)

    def test_resource(self):
        res = resource.Resource("title", [], "foo", "summary")
        self.get_render_and_assert(res)

    def test_resource_mixins(self):
        mixins = [
            mixin.Mixin("foo", "bar", None),
            mixin.Mixin("baz", "foobar", None),
        ]
        res = resource.Resource("title", mixins, "foo", "summary")
        r = self.renderer.get_renderer(res)
        observed = r.render()
        self.assertResourceMixins(res, mixins, observed)

    def test_resource_actions(self):
        actions = [
            action.Action("foo", "bar", None),
            action.Action("baz", "foobar", None),
        ]
        res = resource.Resource("title", [], "foo", "summary")
        res.actions = actions
        r = self.renderer.get_renderer(res)
        observed = r.render()
        self.assertResourceActions(res, actions, observed)

    def test_resource_string_attr(self):
        res = resource.Resource("title", [], "foo", "summary")
        attr = ("org.example.str", "baz")
        res.attributes[attr[0]] = attribute.MutableAttribute(attr[0], attr[1])
        r = self.renderer.get_renderer(res)
        observed = r.render()
        self.assertResourceStringAttr(res, attr, observed)

    def test_resource_int_attr(self):
        res = resource.Resource("title", [], "foo", "summary")
        attr = ("org.example.int", 465)
        res.attributes[attr[0]] = attribute.MutableAttribute(attr[0], attr[1])
        r = self.renderer.get_renderer(res)
        observed = r.render()
        self.assertResourceIntAttr(res, attr, observed)

    def test_resource_bool_attr(self):
        res = resource.Resource("title", [], "foo", "summary")
        attr = ("org.example.bool", True)
        res.attributes[attr[0]] = attribute.MutableAttribute(attr[0], attr[1])
        r = self.renderer.get_renderer(res)
        observed = r.render()
        self.assertResourceBoolAttr(res, attr, observed)

    def test_resource_link(self):
        r1 = resource.Resource(None, [])
        r2 = resource.Resource(None, [])
        r1.link(r2)

        r = self.renderer.get_renderer(r1)
        observed = r.render()
        self.assertResourceLink(r1, r2, observed)

#    def test_action_with_associate_object(self):
#        fake_obj = mock.MagicMock()
#        fake_obj.id = "obj_id"
#        fake_obj.location = "obj_location"
#        fake_obj.kind.term = "obj_term"
#
#        act = action.Action("scheme", "term", "title")
#        r = self.renderer.get_renderer(act)
#        observed = r.render(ass_obj=fake_obj)
#        self.assertExpectedLink(act)
