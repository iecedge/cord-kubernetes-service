
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
import os, sys
import unittest
from mock import patch, PropertyMock, ANY, MagicMock
from unit_test_common import setup_sync_unit_test

def fake_init_kubernetes_client(self):
    self.v1core = MagicMock()
    self.v1apps = MagicMock()
    self.v1batch = MagicMock()

class TestPullPods(unittest.TestCase):

    def setUp(self):
        self.unittest_setup = setup_sync_unit_test(os.path.abspath(os.path.dirname(os.path.realpath(__file__))),
                                                   globals(),
                                                   [("kubernetes-service", "kubernetes.proto")] )

        sys.path.append(os.path.join(os.path.abspath(os.path.dirname(os.path.realpath(__file__))), "../pull_steps"))

        from pull_pods import KubernetesServiceInstancePullStep
        self.pull_step_class = KubernetesServiceInstancePullStep

        self.service = KubernetesService()
        self.trust_domain = TrustDomain(name="test-trust", owner=self.service)
        self.principal = Principal(name="test-principal", trust_domain = self.trust_domain)
        self.image = Image(name="test-image", tag="1.1", kind="container")

    def tearDown(self):
        sys.path = self.unittest_setup["sys_path_save"]

    def test_read_obj_kind(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            pull_step = self.pull_step_class()
            pull_step.v1apps.read_namespaced_replica_set.return_value = ["my_replica_set"]
            pull_step.v1apps.read_namespaced_stateful_set.return_value = ["my_stateful_set"]
            pull_step.v1apps.read_namespaced_daemon_set.return_value = ["my_daemon_set"]
            pull_step.v1apps.read_namespaced_deployment.return_value = ["my_deployment"]
            pull_step.v1batch.read_namespaced_job.return_value = ["my_job"]

            obj = pull_step.read_obj_kind("ReplicaSet", "foo", self.trust_domain)
            self.assertEqual(obj, ["my_replica_set"])

            obj = pull_step.read_obj_kind("StatefulSet", "foo", self.trust_domain)
            self.assertEqual(obj, ["my_stateful_set"])

            obj = pull_step.read_obj_kind("DaemonSet", "foo", self.trust_domain)
            self.assertEqual(obj, ["my_daemon_set"])

            obj = pull_step.read_obj_kind("Deployment", "foo", self.trust_domain)
            self.assertEqual(obj, ["my_deployment"])

            obj = pull_step.read_obj_kind("Job", "foo", self.trust_domain)
            self.assertEqual(obj, ["my_job"])

    def test_get_controller_from_obj(self):
        """ Setup an owner_reference chain: leaf --> StatefulSet --> Deployment. Calling get_controller_from_obj()
            on the leaf should return the deployment.
        """
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            leaf_obj = MagicMock()
            leaf_obj.metadata.owner_references= [MagicMock(controller=True, name="my_stateful_set", kind="StatefulSet")]

            ss_obj = MagicMock()
            ss_obj.metadata.owner_references= [MagicMock(controller=True, name="my_deployment", kind="Deployment")]

            dep_obj = MagicMock()
            dep_obj.metadata.owner_references = []

            pull_step = self.pull_step_class()
            pull_step.v1apps.read_namespaced_stateful_set.return_value = ss_obj
            pull_step.v1apps.read_namespaced_deployment.return_value = dep_obj

            controller = pull_step.get_controller_from_obj(leaf_obj, self.trust_domain)
            self.assertEqual(controller, dep_obj)

    def test_get_slice_from_pod_exists(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client),\
                patch.object(self.pull_step_class, "get_controller_from_obj") as get_controller_from_obj, \
                patch.object(Slice.objects, "get_items") as slice_objects:
            pull_step = self.pull_step_class()

            myslice = Slice(name="myslice")

            dep_obj = MagicMock()
            dep_obj.metadata.name = myslice.name
            get_controller_from_obj.return_value = dep_obj

            slice_objects.return_value = [myslice]

            pod = MagicMock()

            slice = pull_step.get_slice_from_pod(pod, self.trust_domain, self.principal)
            self.assertEqual(slice, myslice)

    def test_get_slice_from_pod_noexist(self):
        """ Call get_slice_from_pod() where not pre-existing slice is present. A new slice will be created, named
            after the pod's controller.
        """
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client),\
                patch.object(self.pull_step_class, "get_controller_from_obj") as get_controller_from_obj, \
                patch.object(Site.objects, "get_items") as site_objects:
            pull_step = self.pull_step_class()

            site_objects.return_value=[Site(name="mysite")]

            dep_obj = MagicMock()
            dep_obj.metadata.name = "my_other_slice"
            get_controller_from_obj.return_value = dep_obj

            pod = MagicMock()

            slice = pull_step.get_slice_from_pod(pod, self.trust_domain, self.principal)
            self.assertEqual(slice.name, "my_other_slice")
            self.assertEqual(slice.trust_domain, self.trust_domain)
            self.assertEqual(slice.principal, self.principal)
            self.assertEqual(slice.xos_managed, False)

    def test_get_trustdomain_from_pod_exists(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client), \
             patch.object(TrustDomain.objects, "get_items") as trustdomain_objects:
            pull_step = self.pull_step_class()

            pod = MagicMock()
            pod.metadata.namespace = self.trust_domain.name

            trustdomain_objects.return_value = [self.trust_domain]

            trustdomain = pull_step.get_trustdomain_from_pod(pod, owner_service=self.service)
            self.assertEqual(trustdomain, self.trust_domain)

    def test_get_trustdomain_from_pod_noexist(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            pull_step = self.pull_step_class()

            pod = MagicMock()
            pod.metadata.namespace = "new-trust"

            trustdomain = pull_step.get_trustdomain_from_pod(pod, owner_service=self.service)
            self.assertEqual(trustdomain.name, "new-trust")
            self.assertEqual(trustdomain.owner, self.service)

    def test_get_principal_from_pod_exists(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client), \
             patch.object(Principal.objects, "get_items") as principal_objects:
            pull_step = self.pull_step_class()

            pod = MagicMock()
            pod.spec.service_account = self.principal.name

            principal_objects.return_value = [self.principal]

            principal = pull_step.get_principal_from_pod(pod, trust_domain=self.trust_domain)
            self.assertEqual(principal, self.principal)

    def test_get_principal_from_pod_noexist(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            pull_step = self.pull_step_class()

            pod = MagicMock()
            pod.spec.service_account = "new-principal"

            principal = pull_step.get_principal_from_pod(pod, trust_domain=self.trust_domain)
            self.assertEqual(principal.name, "new-principal")
            self.assertEqual(principal.trust_domain, self.trust_domain)

    def test_get_image_from_pod_exists(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client), \
             patch.object(Image.objects, "get_items") as image_objects:
            pull_step = self.pull_step_class()

            container = MagicMock()
            container.image = "%s:%s" % (self.image.name, self.image.tag)

            pod = MagicMock()
            pod.spec.containers = [container]

            image_objects.return_value = [self.image]

            image = pull_step.get_image_from_pod(pod)
            self.assertEqual(image, self.image)

    def test_get_image_from_pod_noexist(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            pull_step = self.pull_step_class()

            container = MagicMock()
            container.image = "new-image:2.3" \

            pod = MagicMock()
            pod.spec.containers = [container]

            image = pull_step.get_image_from_pod(pod)
            self.assertEqual(image.name, "new-image")
            self.assertEqual(image.tag, "2.3")
            self.assertEqual(image.kind, "container")

    def make_pod(self, name, trust_domain, principal, image):
        container = MagicMock()
        container.image = "%s:%s" % (image.name, image.tag)

        pod = MagicMock()
        pod.metadata.name = name
        pod.metadata.namespace = trust_domain.name
        pod.spec.service_account = principal.name

        return pod

    def test_pull_records_new_pod(self):
        """ A pod is found in k8s that does not exist in XOS. A new KubernetesServiceInstance sohuld be created
        """
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client), \
             patch.object(self.pull_step_class, "get_trustdomain_from_pod") as get_trustdomain, \
             patch.object(self.pull_step_class, "get_principal_from_pod") as get_principal, \
             patch.object(self.pull_step_class, "get_slice_from_pod") as get_slice, \
             patch.object(self.pull_step_class, "get_image_from_pod") as get_image, \
             patch.object(KubernetesService.objects, "get_items") as service_objects, \
             patch.object(KubernetesServiceInstance.objects, "get_items") as si_objects, \
             patch.object(KubernetesServiceInstance, "save", autospec=True) as ksi_save:

            service_objects.return_value = [self.service]

            slice = Slice(name="myslice")

            get_trustdomain.return_value = self.trust_domain
            get_principal.return_value = self.principal
            get_slice.return_value = slice
            get_image.return_value = self.image

            pod = self.make_pod("my-pod", self.trust_domain, self.principal, self.image)
            pod.status.pod_ip = "1.2.3.4"

            pull_step = self.pull_step_class()
            pull_step.v1core.list_pod_for_all_namespaces.return_value = MagicMock(items=[pod])

            pull_step.pull_records()

            self.assertEqual(ksi_save.call_count, 1)
            saved_ksi = ksi_save.call_args[0][0]

            self.assertEqual(saved_ksi.name, "my-pod")
            self.assertEqual(saved_ksi.pod_ip, "1.2.3.4")
            self.assertEqual(saved_ksi.owner, self.service)
            self.assertEqual(saved_ksi.slice, slice)
            self.assertEqual(saved_ksi.image, self.image)
            self.assertEqual(saved_ksi.xos_managed, False)

    def test_pull_records_missing_pod(self):
        """ A pod is found in k8s that does not exist in XOS. A new KubernetesServiceInstance sohuld be created
        """
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client), \
                patch.object(KubernetesService.objects, "get_items") as service_objects, \
                patch.object(KubernetesServiceInstance.objects, "get_items") as si_objects, \
                patch.object(KubernetesServiceInstance, "delete", autospec=True) as ksi_delete:
            service_objects.return_value = [self.service]

            si = KubernetesServiceInstance(name="my-pod", owner=self.service, xos_managed=False)
            si_objects.return_value = [si]

            pull_step = self.pull_step_class()
            pull_step.v1core.list_pod_for_all_namespaces.return_value = MagicMock(items=[])

            pull_step.pull_records()

            self.assertEqual(ksi_delete.call_count, 1)
            deleted_ksi = ksi_delete.call_args[0][0]

    def test_pull_records_new_pod_kafka_event(self):
        """ A pod is found in k8s that does not exist in XOS. A new KubernetesServiceInstance sohuld be created
        """
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client), \
             patch.object(self.pull_step_class, "get_trustdomain_from_pod") as get_trustdomain, \
             patch.object(self.pull_step_class, "get_principal_from_pod") as get_principal, \
             patch.object(self.pull_step_class, "get_slice_from_pod") as get_slice, \
             patch.object(self.pull_step_class, "get_image_from_pod") as get_image, \
             patch.object(self.pull_step_class, "send_notification", autospec=True) as send_notification, \
             patch.object(KubernetesService.objects, "get_items") as service_objects, \
             patch.object(KubernetesServiceInstance.objects, "get_items") as si_objects, \
             patch.object(KubernetesServiceInstance, "save", autospec=True) as ksi_save:

            service_objects.return_value = [self.service]

            slice = Slice(name="myslice")

            get_trustdomain.return_value = self.trust_domain
            get_principal.return_value = self.principal
            get_slice.return_value = slice
            get_image.return_value = self.image

            pod = self.make_pod("my-pod", self.trust_domain, self.principal, self.image)
            pod.status.pod_ip = "1.2.3.4"

            pull_step = self.pull_step_class()
            pull_step.kafka_producer = "foo"
            pull_step.v1core.list_pod_for_all_namespaces.return_value = MagicMock(items=[pod])

            pull_step.pull_records()

            self.assertEqual(ksi_save.call_count, 2)

            # Inspect the last KubernetesServiceInstance that was saved. There's no way to inspect the first one saved
            # if there are multiple calls, as the sync step will cause the object to be updated.
            saved_ksi = ksi_save.call_args[0][0]
            self.assertEqual(saved_ksi.name, "my-pod")
            self.assertEqual(saved_ksi.pod_ip, "1.2.3.4")
            self.assertEqual(saved_ksi.owner, self.service)
            self.assertEqual(saved_ksi.slice, slice)
            self.assertEqual(saved_ksi.image, self.image)
            self.assertEqual(saved_ksi.xos_managed, False)
            self.assertEqual(saved_ksi.need_event, False)

            self.assertEqual(send_notification.call_count, 1)
            self.assertEqual(send_notification.call_args[0][1], saved_ksi)
            self.assertEqual(send_notification.call_args[0][2], pod)
            self.assertEqual(send_notification.call_args[0][3], "created")

    def test_pull_records_existing_pod_kafka_event(self):
        """ A pod is found in k8s that does not exist in XOS. A new KubernetesServiceInstance sohuld be created
        """
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client), \
             patch.object(self.pull_step_class, "get_trustdomain_from_pod") as get_trustdomain, \
             patch.object(self.pull_step_class, "get_principal_from_pod") as get_principal, \
             patch.object(self.pull_step_class, "get_slice_from_pod") as get_slice, \
             patch.object(self.pull_step_class, "get_image_from_pod") as get_image, \
             patch.object(self.pull_step_class, "send_notification", autospec=True) as send_notification, \
             patch.object(KubernetesService.objects, "get_items") as service_objects, \
             patch.object(KubernetesServiceInstance.objects, "get_items") as si_objects, \
             patch.object(KubernetesServiceInstance, "save", autospec=True) as ksi_save:

            service_objects.return_value = [self.service]

            slice = Slice(name="myslice")

            get_trustdomain.return_value = self.trust_domain
            get_principal.return_value = self.principal
            get_slice.return_value = slice
            get_image.return_value = self.image

            pod = self.make_pod("my-pod", self.trust_domain, self.principal, self.image)
            pod.status.pod_ip = "1.2.3.4"

            xos_pod = KubernetesServiceInstance(name="my-pod",
                                                pod_ip="",
                                                owner=self.service,
                                                slice=slice,
                                                image=self.image,
                                                xos_managed=False,
                                                need_event=False,
                                                last_event_sent="created")
            si_objects.return_value = [xos_pod]

            pull_step = self.pull_step_class()
            pull_step.kafka_producer = "foo"
            pull_step.v1core.list_pod_for_all_namespaces.return_value = MagicMock(items=[pod])

            pull_step.pull_records()

            self.assertEqual(ksi_save.call_count, 2)

            # Inspect the last KubernetesServiceInstance that was saved. There's no way to inspect the first one saved
            # if there are multiple calls, as the sync step will cause the object to be updated.
            saved_ksi = ksi_save.call_args[0][0]
            self.assertEqual(saved_ksi.name, "my-pod")
            self.assertEqual(saved_ksi.pod_ip, "1.2.3.4")
            self.assertEqual(saved_ksi.owner, self.service)
            self.assertEqual(saved_ksi.slice, slice)
            self.assertEqual(saved_ksi.image, self.image)
            self.assertEqual(saved_ksi.xos_managed, False)
            self.assertEqual(saved_ksi.need_event, False)

            self.assertEqual(send_notification.call_count, 1)
            self.assertEqual(send_notification.call_args[0][1], saved_ksi)
            self.assertEqual(send_notification.call_args[0][2], pod)
            self.assertEqual(send_notification.call_args[0][3], "updated")

    def test_send_notification_created(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            pull_step = self.pull_step_class()
            pull_step.kafka_producer = MagicMock()

            pod = self.make_pod("my-pod", self.trust_domain, self.principal, self.image)
            pod.status.pod_ip = "1.2.3.4"
            pod.metadata.labels = {"foo": "bar"}
            xos_pod = KubernetesServiceInstance(name="my-pod",
                                                pod_ip="",
                                                owner=self.service,
                                                slice=slice,
                                                image=self.image,
                                                xos_managed=False,
                                                need_event=False,
                                                last_event_sent="created")
            pull_step.send_notification(xos_pod, pod, "created")

            self.assertEqual(pull_step.kafka_producer.send.call_count, 1)
            topic = pull_step.kafka_producer.send.call_args[0][0]
            event = json.loads(pull_step.kafka_producer.send.call_args[0][1])

            self.assertEqual(topic, "xos.kubernetes.pod-details")

            self.assertEqual(event["name"], "my-pod")
            self.assertEqual(event["status"], "created")
            self.assertEqual(event["producer"], "k8s-sync")
            self.assertEqual(event["labels"], {"foo": "bar"})
            self.assertEqual(event["netinterfaces"], [{"name": "primary", "addresses": ["1.2.3.4"]}])

    def test_send_notification_deleted(self):
        with patch.object(self.pull_step_class, "init_kubernetes_client", new=fake_init_kubernetes_client):
            pull_step = self.pull_step_class()
            pull_step.kafka_producer = MagicMock()

            xos_pod = KubernetesServiceInstance(name="my-pod",
                                                pod_ip="",
                                                owner=self.service,
                                                slice=slice,
                                                image=self.image,
                                                xos_managed=False,
                                                need_event=False,
                                                last_event_sent="created")
            pull_step.send_notification(xos_pod, None, "deleted")

            self.assertEqual(pull_step.kafka_producer.send.call_count, 1)
            topic = pull_step.kafka_producer.send.call_args[0][0]
            event = json.loads(pull_step.kafka_producer.send.call_args[0][1])

            self.assertEqual(topic, "xos.kubernetes.pod-details")

            self.assertEqual(event["name"], "my-pod")
            self.assertEqual(event["status"], "deleted")
            self.assertEqual(event["producer"], "k8s-sync")

if __name__ == '__main__':
    unittest.main()
