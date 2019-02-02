
# Copyright 2017-present Open Networking Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import sys
import unittest
from mock import patch, PropertyMock, ANY, MagicMock
from unit_test_common import setup_sync_unit_test

class ApiException(Exception):
    def __init__(self, status, *args, **kwargs):
        super(ApiException, self).__init__(*args, **kwargs)
        self.status = status

def fake_init_kubernetes_client(self):
    self.kubernetes_client = MagicMock()
    self.v1core = MagicMock()
    self.ApiException = ApiException

class TestSyncService(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.xproto")] )

        self.model_accessor = self.unittest_setup["model_accessor"]

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../steps"))

        self.MockObjectList = self.unittest_setup["MockObjectList"]

        from sync_service import SyncService
        self.step_class = SyncService

        self.trust_domain = TrustDomain(name="test-trust")
        self.service = KubernetesService()

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    def test_get_service_exists(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_service = Service(name="test-service")
            xos_slice = Slice(service=xos_service, trust_domain=self.trust_domain)
            xos_service.slices = self.MockObjectList([xos_slice])

            step = self.step_class(model_accessor = self.model_accessor)
            service = MagicMock()
            step.v1core.read_namespaced_service.return_value = service

            result = step.get_service(xos_service, self.trust_domain.name)

            self.assertEqual(result, service)
            step.v1core.read_namespaced_service.assert_called_with("test-service", "test-trust")

    def test_get_service_noexist(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_service = Service(name="test-service")
            xos_slice = Slice(service=xos_service, trust_domain=self.trust_domain)
            xos_service.slices = self.MockObjectList([xos_slice])

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_service.side_effect = step.ApiException(status=404)

            result = step.get_service(xos_service, self.trust_domain.name)

            self.assertEqual(result, None)

    def test_sync_record_create(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_service = Service(name="test-service")
            xos_slice = Slice(service=xos_service, trust_domain=self.trust_domain)
            xos_service.slices = self.MockObjectList([xos_slice])

            xos_serviceport = ServicePort(service=xos_service, name="web", external_port=123, internal_port=345,
                                          protocol="TCP")
            xos_service.serviceports=self.MockObjectList([xos_serviceport])

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_service.side_effect = step.ApiException(status=404)

            service = MagicMock()
            service.metadata.self_link="1234"
            step.v1core.create_namespaced_service.return_value = service

            step.sync_record(xos_service)

            step.v1core.create_namespaced_service.assert_called()
            self.assertEqual(xos_service.backend_handle, "1234")

    def test_delete_record(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_service = Service(name="test-service")
            xos_slice = Slice(service=xos_service, trust_domain=self.trust_domain)
            xos_service.slices = self.MockObjectList([xos_slice])

            xos_serviceport = ServicePort(service=xos_service, name="web", external_port=123, internal_port=345,
                                          protocol="TCP")
            xos_service.serviceports=self.MockObjectList([xos_serviceport])

            step = self.step_class(model_accessor = self.model_accessor)
            k8s_service = MagicMock()
            step.v1core.read_namespaced_service.return_value = k8s_service
            step.v1core.delete_namespaced_service.return_value = None

            step.delete_record(xos_service)

            step.v1core.delete_namespaced_service.assert_called_with("test-service", self.trust_domain.name, ANY)

if __name__ == '__main__':
    unittest.main()
