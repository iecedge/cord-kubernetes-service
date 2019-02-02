
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

class TestSyncPrincipal(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.xproto")] )

        self.model_accessor = self.unittest_setup["model_accessor"]

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../steps"))

        from sync_principal import SyncPrincipal
        self.step_class = SyncPrincipal

        self.service = KubernetesService()
        self.trust_domain = TrustDomain(owner=self.service, name="test-trust")

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    def test_get_service_account_exists(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_principal = Principal(name="test-principal", trust_domain=self.trust_domain)

            step = self.step_class(model_accessor = self.model_accessor)
            sa = MagicMock()
            step.v1core.read_namespaced_service_account.return_value = sa

            result = step.get_service_account(xos_principal)

            self.assertEqual(result, sa)
            step.v1core.read_namespaced_service_account.assert_called_with("test-principal", "test-trust")

    def test_get_service_account_noexist(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_principal = Principal(name="test-principal", trust_domain=self.trust_domain)

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_service_account.side_effect = step.ApiException(status=404)

            result = step.get_service_account(xos_principal)

            self.assertEqual(result, None)

    def test_sync_record_create(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_principal = Principal(name="test-principal", trust_domain=self.trust_domain)

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_service_account.side_effect = step.ApiException(status=404)

            sa = MagicMock()
            sa.metadata.self_link="1234"
            step.v1core.create_namespaced_service_account.return_value = sa

            step.sync_record(xos_principal)

            step.v1core.create_namespaced_service_account.assert_called()
            self.assertEqual(xos_principal.backend_handle, "1234")

    def test_delete_record(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_principal = Principal(name="test-principal", trust_domain=self.trust_domain)

            step = self.step_class(model_accessor = self.model_accessor)
            k8s_sa = MagicMock()
            step.v1core.read_namespaced_service_account.return_value = k8s_sa

            step.delete_record(xos_principal)

            step.v1core.delete_namespaced_service_account.assert_called_with("test-principal", self.trust_domain.name, ANY)

if __name__ == '__main__':
    unittest.main()
