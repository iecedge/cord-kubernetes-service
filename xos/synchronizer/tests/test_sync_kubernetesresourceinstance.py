
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
from mock import patch, PropertyMock, ANY, MagicMock, Mock
from unit_test_common import setup_sync_unit_test

class ApiException(Exception):
    def __init__(self, status, *args, **kwargs):
        super(ApiException, self).__init__(*args, **kwargs)
        self.status = status

def fake_init_kubernetes_client(self):
    self.kubernetes_client = MagicMock()
    self.v1core = MagicMock()
    self.ApiException = ApiException

class TestSyncKubernetesResourceInstance(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.proto")] )

        self.MockObjectList = self.unittest_setup["MockObjectList"]

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../steps"))

        from sync_kubernetesresourceinstance import SyncKubernetesResourceInstance
        self.step_class = SyncKubernetesResourceInstance

        self.service = KubernetesService()

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    @patch('subprocess.Popen')
    def test_run_kubectl(self, mock_popen):
        proc = Mock()
        proc.communicate.return_value = ('output', 'error')
        proc.returncode = 0

        mock_popen.return_value = proc

        step = self.step_class()
        step.run_kubectl("create", "foo")

        mock_popen.assert_called()

    @patch('subprocess.Popen')
    def test_run_kubectl_fail(self, mock_popen):
        proc = Mock()
        proc.communicate.return_value = ('output', 'error')
        proc.returncode = 1

        mock_popen.return_value = proc

        step = self.step_class()
        with self.assertRaises(Exception) as e:
          step.run_kubectl("create", "foo")

        self.assertEqual(e.exception.message, "Process failed with returncode 1")

    def test_sync_record_create(self):
        with patch.object(self.step_class, "run_kubectl") as run_kubectl:
            xos_ri = KubernetesResourceInstance(name="test-instance", owner=self.service, resource_definition="foo")

            run_kubectl.return_value = None

            step = self.step_class()
            step.sync_record(xos_ri)

            run_kubectl.assert_called_with("apply", "foo")

            self.assertEqual(xos_ri.kubectl_state, "created")

    def test_sync_record_update(self):
        with patch.object(self.step_class, "run_kubectl") as run_kubectl:
            xos_ri = KubernetesResourceInstance(name="test-instance", owner=self.service, resource_definition="foo", kubectl_state="created")

            run_kubectl.return_value = None

            step = self.step_class()
            step.sync_record(xos_ri)

            run_kubectl.assert_called_with("apply", "foo")

            self.assertEqual(xos_ri.kubectl_state, "updated")

    def test_sync_record_delete(self):
        with patch.object(self.step_class, "run_kubectl") as run_kubectl:
            xos_ri = KubernetesResourceInstance(name="test-instance", owner=self.service, resource_definition="foo", kubectl_state="created")

            run_kubectl.return_value = None

            step = self.step_class()
            step.delete_record(xos_ri)

            run_kubectl.assert_called_with("delete", "foo")

            self.assertEqual(xos_ri.kubectl_state, "deleted")

    def test_sync_record_delete_never_created(self):
        """ If the object was never saved, then we shouldn't try to delete it """
        with patch.object(self.step_class, "run_kubectl") as run_kubectl:
            xos_ri = KubernetesResourceInstance(name="test-instance", owner=self.service, resource_definition="foo")

            run_kubectl.return_value = None

            step = self.step_class()
            step.delete_record(xos_ri)

            run_kubectl.assert_not_called()


if __name__ == '__main__':
    unittest.main()
