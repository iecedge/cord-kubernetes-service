
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
    sync_configmap.py

    Synchronize Config Maps.
"""

import json
from xossynchronizer.steps.syncstep import SyncStep
from xossynchronizer.modelaccessor import KubernetesConfigMap

from xosconfig import Config
from multistructlog import create_logger

log = create_logger(Config().get('logging'))

class SyncKubernetesConfigMap(SyncStep):

    """
        SyncKubernetesConfigMap

        Implements sync step for syncing ConfigMaps.
    """

    provides = [KubernetesConfigMap]
    observes = KubernetesConfigMap
    requested_interval = 0

    def __init__(self, *args, **kwargs):
        super(SyncKubernetesConfigMap, self).__init__(*args, **kwargs)
        self.init_kubernetes_client()

    def init_kubernetes_client(self):
        from kubernetes import client as kubernetes_client, config as kubernetes_config
        from kubernetes.client.rest import ApiException
        kubernetes_config.load_incluster_config()
        self.kubernetes_client = kubernetes_client
        self.v1core = kubernetes_client.CoreV1Api()
        self.ApiException = ApiException

    def get_config_map(self, o):
        """ Given an XOS KubernetesConfigMap object, read the corresponding ConfigMap from Kubernetes.
            return None if no ConfigMap exists.
        """
        try:
            config_map = self.v1core.read_namespaced_config_map(o.name, o.trust_domain.name)
        except self.ApiException, e:
            if e.status == 404:
                return None
            raise
        return config_map

    def sync_record(self, o):
            config_map = self.get_config_map(o)
            if not config_map:
                config_map = self.kubernetes_client.V1ConfigMap()
                config_map.data = json.loads(o.data)
                config_map.metadata = self.kubernetes_client.V1ObjectMeta(name=o.name)

                config_map = self.v1core.create_namespaced_config_map(o.trust_domain.name, config_map)
            else:
                config_map.data = json.loads(o.data)
                self.v1core.patch_namespaced_config_map(o.name, o.trust_domain.name, config_map)

            if (not o.backend_handle):
                o.backend_handle = config_map.metadata.self_link
                o.save(update_fields=["backend_handle"])

    def delete_record(self, o):
        config_map = self.get_config_map(o)
        if not config_map:
            log.info("Kubernetes config map does not exist; Nothing to delete.", o=o)
            return
        delete_options = self.kubernetes_client.V1DeleteOptions()
        self.v1core.delete_namespaced_config_map(o.name, o.trust_domain.name, delete_options)
        log.info("Deleted configmap from kubernetes", handle=o.backend_handle)




