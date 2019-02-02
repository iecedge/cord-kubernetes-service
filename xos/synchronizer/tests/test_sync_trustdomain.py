
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

class TestSyncTrustDomain(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.xproto")] )

        self.model_accessor = self.unittest_setup["model_accessor"]

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../steps"))

        from sync_trustdomain import SyncTrustDomain
        self.step_class = SyncTrustDomain

        self.service = KubernetesService()

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    def test_get_namespace_exists(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_trustdomain = TrustDomain(name="test-trust")

            step = self.step_class(model_accessor=self.model_accessor)
            td = MagicMock()
            step.v1core.read_namespace.return_value = td

            result = step.get_namespace(xos_trustdomain)

            self.assertEqual(result, td)
            step.v1core.read_namespace.assert_called_with("test-trust")

    def test_get_config_namespace_noexist(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_trustdomain = TrustDomain(name="test-trust")

            step = self.step_class(model_accessor=self.model_accessor)
            step.v1core.read_namespace.side_effect = step.ApiException(status=404)

            result = step.get_namespace(xos_trustdomain)

            self.assertEqual(result, None)

    def test_sync_record_create(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_trustdomain = TrustDomain(name="test-trust")

            step = self.step_class(model_accessor=self.model_accessor)
            step.v1core.read_namespace.side_effect = step.ApiException(status=404)

            td = MagicMock()
            td.metadata.self_link="1234"
            step.v1core.create_namespace.return_value = td

            step.sync_record(xos_trustdomain)

            step.v1core.create_namespace.assert_called()
            self.assertEqual(xos_trustdomain.backend_handle, "1234")

    def test_delete_record(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_trustdomain = TrustDomain(name="test-trust")

            step = self.step_class(model_accessor=self.model_accessor)
            td = MagicMock()
            step.v1core.read_namespace.return_value = td

            step.delete_record(xos_trustdomain)

            step.v1core.delete_namespace.assert_called_with("test-trust", ANY)

if __name__ == '__main__':
    unittest.main()
