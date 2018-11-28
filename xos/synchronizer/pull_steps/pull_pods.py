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

"""
    pull_pods.py

    Implements a syncstep to pull information about pods form Kubernetes.
"""

import json

from synchronizers.new_base.pullstep import PullStep
from synchronizers.new_base.modelaccessor import KubernetesServiceInstance, KubernetesService, Slice, Principal, \
                                                 TrustDomain, Site, Image

from xosconfig import Config
from multistructlog import create_logger
from xoskafka import XOSKafkaProducer

log = create_logger(Config().get('logging'))


class KubernetesServiceInstancePullStep(PullStep):
    """
         KubernetesServiceInstancePullStep

         Pull pod-related information from Kubernetes. Each pod we find is used to create a KubernetesServiceInstance
         if one does not already exist. Additional support objects (Slices, TrustDomains, Principals) may be created
         as necessary to fill the required dependencies of the KubernetesServiceInstance.
    """

    def __init__(self):
        super(KubernetesServiceInstancePullStep, self).__init__(observed_model=KubernetesServiceInstance)

        self.init_kubernetes_client()

    def init_kubernetes_client(self):
        from kubernetes import client as kubernetes_client, config as kubernetes_config
        kubernetes_config.load_incluster_config()
        self.v1core = kubernetes_client.CoreV1Api()
        self.v1apps = kubernetes_client.AppsV1Api()
        self.v1batch = kubernetes_client.BatchV1Api()

    def obj_to_handle(self, obj):
        """ Convert a Kubernetes resource into a handle that we can use to uniquely identify the object within
            Kubernetes.
        """
        return obj.metadata.self_link

    def read_obj_kind(self, kind, name, trust_domain):
        """ Given an object kind and name, read it from Kubernetes """
        if kind == "ReplicaSet":
            resource = self.v1apps.read_namespaced_replica_set(name, trust_domain.name)
        elif kind == "StatefulSet":
            resource = self.v1apps.read_namespaced_stateful_set(name, trust_domain.name)
        elif kind == "DaemonSet":
            resource = self.v1apps.read_namespaced_daemon_set(name, trust_domain.name)
        elif kind == "Deployment":
            resource = self.v1apps.read_namespaced_deployment(name, trust_domain.name)
        elif kind == "Job":
            resource = self.v1batch.read_namespaced_job(name, trust_domain.name)
        else:
            resource = None
        return resource

    def get_controller_from_obj(self, obj, trust_domain, depth=0):
        """ Given an object, Search for its controller. Strategy is to walk backward until we find some object that
            is marked as a controller, but does not have any owners.

            This seems adequate to cover the case where ReplicaSet is owned by a Deployment, and we want to skup over
            the ReplicaSet and return the Deployment.
        """

        owner_references = obj.metadata.owner_references
        if not owner_references:
            if (depth==0):
                # If depth is zero, then we're still looking at the object, not a controller.
                return None
            return obj

        for owner_reference in owner_references:
            if not getattr(owner_reference, "controller", False):
                continue
            owner = self.read_obj_kind(owner_reference.kind, owner_reference.name, trust_domain)
            if not owner:
                # Failed to fetch the owner, probably because the owner's kind is something we do not understand. An
                # example is the etcd-cluser pod, which is owned by a deployment of kind "EtcdCluster".
                log.debug("failed to fetch owner", owner_reference=owner_reference)
                continue
            controller = self.get_controller_from_obj(owner, trust_domain, depth+1)
            if controller:
                return controller

        return None

    def get_slice_from_pod(self, pod, trust_domain, principal):
        """ Given a pod, determine which XOS Slice goes with it
            If the Slice doesn't exist, create it.
        """
        controller = self.get_controller_from_obj(pod, trust_domain)
        if not controller:
            return None

        slice_name = controller.metadata.name
        if hasattr(controller.metadata, "labels") and controller.metadata.labels is not None:
            if "xos_slice_name" in controller.metadata.labels:
                # Someone has labeled the controller with an xos slice name. Use it.
                slice_name = controller.metadata.labels["xos_slice_name"]

        existing_slices = Slice.objects.filter(name = slice_name)
        if not existing_slices:
            # TODO(smbaker): atomicity
            s = Slice(name=slice_name, site = Site.objects.first(),
                      trust_domain=trust_domain,
                      principal=principal,
                      backend_handle=self.obj_to_handle(controller),
                      controller_kind=controller.kind,
                      xos_managed=False)
            s.save()
            return s
        else:
            return existing_slices[0]

    def get_trustdomain_from_pod(self, pod, owner_service):
        """ Given a pod, determine which XOS TrustDomain goes with it
            If the TrustDomain doesn't exist, create it.
        """
        existing_trustdomains = TrustDomain.objects.filter(name = pod.metadata.namespace)
        if not existing_trustdomains:
            k8s_trust_domain = self.v1core.read_namespace(pod.metadata.namespace)

            # TODO(smbaker): atomicity
            t = TrustDomain(name = pod.metadata.namespace,
                            xos_managed=False,
                            owner=owner_service,
                            backend_handle = self.obj_to_handle(k8s_trust_domain))
            t.save()
            return t
        else:
            return existing_trustdomains[0]

    def get_principal_from_pod(self, pod, trust_domain):
        """ Given a pod, determine which XOS Principal goes with it
            If the Principal doesn't exist, create it.
        """
        principal_name = getattr(pod.spec, "service_account", None)
        if not principal_name:
            return None
        existing_principals = Principal.objects.filter(name = principal_name)
        if not existing_principals:
            k8s_service_account = self.v1core.read_namespaced_service_account(principal_name, trust_domain.name)

            # TODO(smbaker): atomicity
            p = Principal(name = principal_name,
                          trust_domain = trust_domain,
                          xos_managed = False,
                          backend_handle = self.obj_to_handle(k8s_service_account))
            p.save()
            return p
        else:
            return existing_principals[0]

    def get_image_from_pod(self, pod):
        """ Given a pod, determine which XOS Image goes with it
            If the Image doesn't exist, create it.
        """
        containers = pod.spec.containers
        if containers:
            # TODO(smbaker): Assumes all containers in a pod use the same image. Valid assumption for now?
            container = containers[0]
            if ":" in container.image:
                (name, tag) = container.image.rsplit(":", 1)
            else:
                # Is assuming a default necessary?
                name = container.image
                tag = "master"

            existing_images = Image.objects.filter(name=name, tag=tag, kind="container")
            if not existing_images:
                i = Image(name=name, tag=tag, kind="container", xos_managed=False)
                i.save()
                return i
            else:
                return existing_images[0]
        else:
            return None

    def send_notification(self, xos_pod, k8s_pod, status):

        event = {"status": status,
                 "name": xos_pod.name,
                 "producer": "k8s-sync"}

        if xos_pod.id:
            event["kubernetesserviceinstance_id"] = xos_pod.id

        if k8s_pod:
            event["labels"] = k8s_pod.metadata.labels

            if k8s_pod.status.pod_ip:
                event["netinterfaces"] = [{"name": "primary",
                                          "addresses": [k8s_pod.status.pod_ip]}]

        topic = "xos.kubernetes.pod-details"
        key = xos_pod.name
        value = json.dumps(event, default=lambda o: repr(o))

        XOSKafkaProducer.produce(topic, key, value)


    def pull_records(self):
        # Read all pods from Kubernetes, store them in k8s_pods_by_name
        k8s_pods_by_name = {}
        ret = self.v1core.list_pod_for_all_namespaces(watch=False)
        for item in ret.items:
            k8s_pods_by_name[item.metadata.name] = item

        # Read all pods from XOS, store them in xos_pods_by_name
        xos_pods_by_name = {}
        existing_pods = KubernetesServiceInstance.objects.all()
        for pod in existing_pods:
            xos_pods_by_name[pod.name] = pod

        kubernetes_services = KubernetesService.objects.all()
        if len(kubernetes_services)==0:
            raise Exception("There are no Kubernetes Services yet")
        if len(kubernetes_services)>1:
            # Simplifying assumption -- there is only one Kubernetes Service
            raise Exception("There are too many Kubernetes Services")
        kubernetes_service = kubernetes_services[0]

        # For each k8s pod, see if there is an xos pod. If there is not, then create the xos pod.
        for (k,pod) in k8s_pods_by_name.items():
            try:
                if not k in xos_pods_by_name:
                    trust_domain = self.get_trustdomain_from_pod(pod, owner_service=kubernetes_service)
                    if not trust_domain:
                        # All kubernetes pods should belong to a namespace. If we can't find the namespace, then
                        # something is very wrong in K8s.
                        log.warning("Unable to determine trust_domain for pod %s. Ignoring." % k)
                        continue

                    principal = self.get_principal_from_pod(pod, trust_domain)
                    slice = self.get_slice_from_pod(pod, trust_domain=trust_domain, principal=principal)
                    image = self.get_image_from_pod(pod)

                    if not slice:
                        # We could get here if the pod doesn't have a controller, or if the controller is of a kind
                        # that we don't understand (such as the Etcd controller). If so, the pod is not something we
                        # are interested in.
                        log.debug("Unable to determine slice for pod %s. Ignoring." % k)
                        continue

                    xos_pod = KubernetesServiceInstance(name=k,
                                                        pod_ip = pod.status.pod_ip,
                                                        owner = kubernetes_service,
                                                        slice = slice,
                                                        image = image,
                                                        backend_handle = self.obj_to_handle(pod),
                                                        xos_managed = False,
                                                        need_event = True)
                    xos_pod.save()
                    xos_pods_by_name[k] = xos_pod
                    log.info("Created XOS POD %s" % xos_pod.name)

                xos_pod = xos_pods_by_name[k]

                # Check to see if the ip address has changed. This can happen for pods that are managed by XOS. The IP
                # isn't available immediately when XOS creates a pod, but shows up a bit later. So handle that case
                # here.
                if (pod.status.pod_ip is not None) and (xos_pod.pod_ip != pod.status.pod_ip):
                    xos_pod.pod_ip = pod.status.pod_ip
                    xos_pod.need_event = True # Trigger a new kafka event
                    xos_pod.save(update_fields = ["pod_ip", "need_event"])
                    log.info("Updated XOS POD %s" % xos_pod.name)

                # Check to see if we haven't sent the Kafka event yet. It's possible Kafka could be down. If
                # so, then we'll try to send the event again later.
                if (xos_pod.need_event):
                    if xos_pod.last_event_sent == "created":
                        event_kind = "updated"
                    else:
                        event_kind = "created"

                    self.send_notification(xos_pod, pod, event_kind)

                    xos_pod.need_event = False
                    xos_pod.last_event_sent = event_kind
                    xos_pod.save(update_fields=["need_event", "last_event_sent"])

            except:
                log.exception("Failed to process k8s pod", k=k, pod=pod)

        # For each xos pod, see if there is no k8s pod. If that's the case, then the pud must have been deleted.
        for (k,xos_pod) in xos_pods_by_name.items():
            try:
                if (not k in k8s_pods_by_name):
                    if (xos_pod.xos_managed):
                        # Should we do something so it gets re-created by the syncstep?
                        pass
                    else:
                        self.send_notification(xos_pod, None, "deleted")
                        xos_pod.delete()
                        log.info("Deleted XOS POD %s" % k)
            except:
                log.exception("Failed to process xos pod", k=k, xos_pod=xos_pod)
