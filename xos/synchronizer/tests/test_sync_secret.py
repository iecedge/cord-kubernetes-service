
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

class TestSyncSecret(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.xproto")] )

        self.model_accessor = self.unittest_setup["model_accessor"]

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../steps"))

        from sync_secret import SyncKubernetesSecret
        self.step_class = SyncKubernetesSecret

        self.service = KubernetesService()
        self.trust_domain = TrustDomain(name="test-trust", owner=self.service)

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    def test_get_secret_exists(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_secret = KubernetesSecret(trust_domain=self.trust_domain, name="test-secret")

            step = self.step_class(model_accessor = self.model_accessor)
            secret = MagicMock()
            step.v1core.read_namespaced_secret.return_value = secret

            result = step.get_secret(xos_secret)

            self.assertEqual(result, secret)
            step.v1core.read_namespaced_secret.assert_called_with("test-secret", "test-trust")

    def test_get_secret_noexist(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_secret = KubernetesSecret(trust_domain=self.trust_domain, name="test-secret")

            step = self.step_class(model_accessor = self.model_accessor)
            secret = MagicMock()
            step.v1core.read_namespaced_secret.side_effect = step.ApiException(status=404)

            result = step.get_secret(xos_secret)

            self.assertEqual(result, None)

    def test_sync_record_create(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            data = {"foo": "bar"}
            xos_secret = KubernetesSecret(trust_domain=self.trust_domain, name="test-secret", data=json.dumps(data))

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_secret.side_effect = step.ApiException(status=404)

            secret = MagicMock()
            secret.metadata.self_link="1234"
            step.v1core.create_namespaced_secret.return_value = secret

            step.sync_record(xos_secret)

            step.v1core.create_namespaced_secret.assert_called()
            self.assertEqual(xos_secret.backend_handle, "1234")

    def test_sync_record_update(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            data = {"foo": "bar"}
            xos_secret = KubernetesSecret(trust_domain=self.trust_domain, name="test-secret", data=json.dumps(data))

            orig_secret = MagicMock()
            orig_secret.data = {"foo": "not_bar"}
            orig_secret.metadata.self_link = "1234"

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_secret.return_value = orig_secret

            new_secret = MagicMock()
            new_secret.data = {"foo": "bar"}
            new_secret.metadata.self_link = "1234"

            step.v1core.patch_namespaced_secret.return_value = new_secret

            step.sync_record(xos_secret)

            self.assertEqual(step.v1core.patch_namespaced_secret.call_count, 1)
            call_args = step.v1core.patch_namespaced_secret.call_args[0]
            self.assertEqual(call_args[0], "test-secret")
            self.assertEqual(call_args[1], "test-trust")
            self.assertEqual(call_args[2].data, {"foo": "bar"})

            self.assertEqual(xos_secret.backend_handle, "1234")

    def test_delete_record(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            data = {"foo": "bar"}
            xos_secret = KubernetesSecret(trust_domain=self.trust_domain, name="test-secret", data=json.dumps(data))

            orig_secret = MagicMock()
            orig_secret.data = {"foo": "not_bar"}
            orig_secret.metadata.self_link = "1234"

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_secret.return_value = orig_secret

            step.delete_record(xos_secret)

            step.v1core.delete_namespaced_secret.assert_called_with("test-secret", self.trust_domain.name, ANY)


if __name__ == '__main__':
    unittest.main()
