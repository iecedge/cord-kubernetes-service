
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

class TestSyncKubernetesServiceInstance(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.xproto")] )

        self.MockObjectList = self.unittest_setup["MockObjectList"]
        self.model_accessor = self.unittest_setup["model_accessor"]

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../steps"))

        from sync_kubernetesserviceinstance import SyncKubernetesServiceInstance
        self.step_class = SyncKubernetesServiceInstance

        self.service = KubernetesService()
        self.trust_domain = TrustDomain(owner=self.service, name="test-trust")
        self.principal = Principal(name="test-principal", trust_domain=self.trust_domain)
        self.slice = Slice(name="test-slice", trust_domain=self.trust_domain, principal=self.principal)
        self.image = Image(name="test-image", tag="1.2", kind="container")

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    def test_get_pod_exists(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_si = KubernetesServiceInstance(name="test-instance", slice=self.slice)

            step = self.step_class(model_accessor = self.model_accessor)
            pod = MagicMock()
            step.v1core.read_namespaced_pod.return_value = pod

            result = step.get_pod(xos_si)

            self.assertEqual(result, pod)
            step.v1core.read_namespaced_pod.assert_called_with("test-instance", "test-trust")

    def test_get_pod_noexist(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_si = KubernetesServiceInstance(name="test-instance", slice=self.slice)

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_pod.side_effect = step.ApiException(status=404)

            result = step.get_pod(xos_si)

            self.assertEqual(result, None)

    def test_sync_record_create(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_si = KubernetesServiceInstance(name="test-instance", slice=self.slice, image=self.image)
            xos_si.kubernetes_config_volume_mounts = self.MockObjectList([])
            xos_si.kubernetes_secret_volume_mounts = self.MockObjectList([])

            step = self.step_class(model_accessor = self.model_accessor)
            step.v1core.read_namespaced_pod.side_effect = step.ApiException(status=404)

            pod = MagicMock()
            pod.metadata.self_link="1234"
            step.v1core.create_namespaced_pod.return_value = pod

            step.sync_record(xos_si)

            step.v1core.create_namespaced_pod.assert_called()
            self.assertEqual(xos_si.backend_handle, "1234")

    def test_delete_record(self):
        with patch.object(self.step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            xos_si = KubernetesServiceInstance(name="test-instance", slice=self.slice, image=self.image)
            xos_si.kubernetes_config_volume_mounts = self.MockObjectList([])
            xos_si.kubernetes_secret_volume_mounts = self.MockObjectList([])

            step = self.step_class(model_accessor = self.model_accessor)
            pod = MagicMock()
            step.v1core.read_namespaced_pod.return_value = pod

            step.delete_record(xos_si)
            step.v1core.delete_namespaced_pod.assert_called_with("test-instance", self.trust_domain.name, ANY)

if __name__ == '__main__':
    unittest.main()
