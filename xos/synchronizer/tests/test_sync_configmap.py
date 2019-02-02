
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

class TestSyncConfigmap(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.xproto")] )

        self.model_accessor = self.unittest_setup["model_accessor"]

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../steps"))

        from sync_configmap import SyncKubernetesConfigMap
        self.step_class = SyncKubernetesConfigMap

        self.service = KubernetesService()
        self.trust_domain = TrustDomain(name="test-trust", owner=self.service)

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    def test_get_config_map_exists(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            configmap = KubernetesConfigMap(trust_domain=self.trust_domain, name="test-configmap")

            step = self.step_class(model_accessor = self.model_accessor)
            map = MagicMock()
            step.v1core.read_namespaced_config_map.return_value = map

            result = step.get_config_map(configmap)

            self.assertEqual(result, map)
            step.v1core.read_namespaced_config_map.assert_called_with("test-configmap", "test-trust")

    def test_get_config_map_noexist(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            configmap = KubernetesConfigMap(trust_domain=self.trust_domain, name="test-configmap")

            step = self.step_class(model_accessor = self.model_accessor)
            map = MagicMock()
            step.v1core.read_namespaced_config_map.side_effect = step.ApiException(status=404)

            result = step.get_config_map(configmap)

            self.assertEqual(result, None)

    def test_sync_record_create(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            data = {"foo": "bar"}
            configmap = KubernetesConfigMap(trust_domain=self.trust_domain, name="test-configmap", data=json.dumps(data))

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_config_map.side_effect = step.ApiException(status=404)

            map = MagicMock()
            map.metadata.self_link="1234"
            step.v1core.create_namespaced_config_map.return_value = map

            step.sync_record(configmap)

            step.v1core.create_namespaced_config_map.assert_called()
            self.assertEqual(configmap.backend_handle, "1234")

    def test_sync_record_update(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            data = {"foo": "bar"}
            configmap = KubernetesConfigMap(trust_domain=self.trust_domain, name="test-configmap", data=json.dumps(data))

            orig_map = MagicMock()
            orig_map.data = {"foo": "not_bar"}
            orig_map.metadata.self_link = "1234"

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_config_map.return_value = orig_map

            new_map = MagicMock()
            new_map.data = {"foo": "bar"}
            new_map.metadata.self_link = "1234"

            step.v1core.patch_namespaced_config_map.return_value = new_map

            step.sync_record(configmap)

            self.assertEqual(step.v1core.patch_namespaced_config_map.call_count, 1)
            call_args = step.v1core.patch_namespaced_config_map.call_args[0]
            self.assertEqual(call_args[0], "test-configmap")
            self.assertEqual(call_args[1], "test-trust")
            self.assertEqual(call_args[2].data, {"foo": "bar"})

            self.assertEqual(configmap.backend_handle, "1234")

    def test_delete_record(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            data = {"foo": "bar"}
            configmap = KubernetesConfigMap(trust_domain=self.trust_domain, name="test-configmap", data=json.dumps(data))

            orig_map = MagicMock()
            orig_map.data = {"foo": "not_bar"}
            orig_map.metadata.self_link = "1234"

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_config_map.return_value = orig_map

            step.delete_record(configmap)

            step.v1core.delete_namespaced_config_map.assert_called_with("test-configmap", self.trust_domain.name, ANY)




if __name__ == '__main__':
    unittest.main()
