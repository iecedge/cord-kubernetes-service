
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
    sync_kubernetesserviceinstance.py

    Synchronize KubernetesServiceInstance. See also the related pull_step.

    This sync_step is intended to handle the case where callers are creating pods directly, as opposed to using
    a controller to manage pods for them. It makes some simplifying assumptions, such as each pod has one
    container and uses one image.
"""

from xossynchronizer.steps.syncstep import SyncStep
from xossynchronizer.modelaccessor import KubernetesServiceInstance

from xosconfig import Config
from multistructlog import create_logger

log = create_logger(Config().get('logging'))

class SyncKubernetesServiceInstance(SyncStep):

    """
        SyncKubernetesServiceInstance

        Implements sync step for syncing kubernetes service instances.
    """

    provides = [KubernetesServiceInstance]
    observes = KubernetesServiceInstance
    requested_interval = 0

    def __init__(self, *args, **kwargs):
        super(SyncKubernetesServiceInstance, self).__init__(*args, **kwargs)
        self.init_kubernetes_client()

    def init_kubernetes_client(self):
        from kubernetes.client.rest import ApiException
        from kubernetes import client as kubernetes_client, config as kubernetes_config
        kubernetes_config.load_incluster_config()
        self.kubernetes_client = kubernetes_client
        self.v1core = kubernetes_client.CoreV1Api()
        self.ApiException = ApiException

    def get_pod(self, o):
        """ Given a KubernetesServiceInstance, read the pod from Kubernetes.
            Return None if the pod does not exist.
        """
        try:
            pod = self.v1core.read_namespaced_pod(o.name, o.slice.trust_domain.name)
        except self.ApiException, e:
            if e.status == 404:
                return None
            raise
        return pod

    def generate_pod_spec(self, o):
        pod = self.kubernetes_client.V1Pod()
        pod.metadata = self.kubernetes_client.V1ObjectMeta(name=o.name)

        if o.slice.trust_domain:
            pod.metadata.namespace = o.slice.trust_domain.name

        if o.image.tag:
            imageName = o.image.name + ":" + o.image.tag
        else:
            # TODO(smbaker): Is this case possible?
            imageName = o.image.name

        volumes = []
        volume_mounts = []

        # Attach and mount the configmaps
        for xos_vol in o.kubernetes_config_volume_mounts.all():
            k8s_vol = self.kubernetes_client.V1Volume(name=xos_vol.config.name)
            k8s_vol.config_map = self.kubernetes_client.V1ConfigMapVolumeSource(name=xos_vol.config.name)
            volumes.append(k8s_vol)

            k8s_vol_m = self.kubernetes_client.V1VolumeMount(name=xos_vol.config.name,
                                                        mount_path=xos_vol.mount_path,
                                                        sub_path=xos_vol.sub_path)
            volume_mounts.append(k8s_vol_m)

        # Attach and mount the secrets
        for xos_vol in o.kubernetes_secret_volume_mounts.all():
            k8s_vol = self.kubernetes_client.V1Volume(name=xos_vol.secret.name)
            k8s_vol.secret = self.kubernetes_client.V1SecretVolumeSource(secret_name=xos_vol.secret.name)
            volumes.append(k8s_vol)

            k8s_vol_m = self.kubernetes_client.V1VolumeMount(name=xos_vol.secret.name,
                                                        mount_path=xos_vol.mount_path,
                                                        sub_path=xos_vol.sub_path)
            volume_mounts.append(k8s_vol_m)

        container = self.kubernetes_client.V1Container(name=o.name,
                                                  image=imageName,
                                                  volume_mounts=volume_mounts)

        spec = self.kubernetes_client.V1PodSpec(containers=[container], volumes=volumes)
        pod.spec = spec

        if o.slice.principal:
            pod.spec.service_account = o.slice.principal.name

        return pod

    def sync_record(self, o):
        if o.xos_managed:
            if (not o.slice) or (not o.slice.trust_domain):
                raise Exception("No trust domain for service instance", o=o)

            if (not o.name):
                raise Exception("No name for service instance")

            pod = self.get_pod(o)
            if not pod:
                pod = self.generate_pod_spec(o)

                log.info("Creating pod", o=o, pod=pod)

                pod = self.v1core.create_namespaced_pod(o.slice.trust_domain.name, pod)
            else:
                log.info("Replacing pod", o=o, pod=pod)

                # TODO: apply changes, perhaps by calling self.generate_pod_spec() and copying in the differences,
                # to accomodate new volumes that might have been attached, or other changes.

                # If we don't apply any changes to the pod, it's still the case that Kubernetes will pull in new
                # mounts of existing configmaps during the replace operation, if the configmap contents have changed.

                pod = self.v1core.replace_namespaced_pod(o.name, o.slice.trust_domain.name, pod)

            if (not o.backend_handle):
                o.backend_handle = pod.metadata.self_link
                o.save(update_fields=["backend_handle"])

    def delete_record(self, o):
        secret = self.get_pod(o)
        if not secret:
            log.info("Kubernetes pod does not exist; Nothing to delete.", o=o)
            return
        delete_options = self.kubernetes_client.V1DeleteOptions()
        self.v1core.delete_namespaced_pod(o.name, o.slice.trust_domain.name, delete_options)
        log.info("Deleted pod from kubernetes", handle=o.backend_handle)


