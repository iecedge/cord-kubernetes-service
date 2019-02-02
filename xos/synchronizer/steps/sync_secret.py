
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
    sync_secret.py

    Synchronize Secrets.
"""

import json
from xossynchronizer.steps.syncstep import SyncStep
from xossynchronizer.modelaccessor import KubernetesSecret

from xosconfig import Config
from multistructlog import create_logger

log = create_logger(Config().get('logging'))

class SyncKubernetesSecret(SyncStep):

    """
        SyncKubernetesSecret

        Implements sync step for syncing Secrets.
    """

    provides = [KubernetesSecret]
    observes = KubernetesSecret
    requested_interval = 0

    def __init__(self, *args, **kwargs):
        super(SyncKubernetesSecret, self).__init__(*args, **kwargs)
        self.init_kubernetes_client()

    def init_kubernetes_client(self):
        from kubernetes.client.rest import ApiException
        from kubernetes import client as kubernetes_client, config as kubernetes_config
        kubernetes_config.load_incluster_config()
        self.kubernetes_client = kubernetes_client
        self.v1core = kubernetes_client.CoreV1Api()
        self.ApiException = ApiException

    def get_secret(self, o):
        """ Given an XOS KubernetesSecret object, read the corresponding Secret from Kubernetes.
            return None if no Secret exists.
        """
        try:
            secret = self.v1core.read_namespaced_secret(o.name, o.trust_domain.name)
        except self.ApiException, e:
            if e.status == 404:
                return None
            raise
        return secret

    def sync_record(self, o):
            secret = self.get_secret(o)
            if not secret:
                secret = self.kubernetes_client.V1Secret()
                secret.data = json.loads(o.data)
                secret.metadata = self.kubernetes_client.V1ObjectMeta(name=o.name)

                secret = self.v1core.create_namespaced_secret(o.trust_domain.name, secret)
            else:
                secret.data = json.loads(o.data)
                self.v1core.patch_namespaced_secret(o.name, o.trust_domain.name, secret)

            if (not o.backend_handle):
                o.backend_handle = secret.metadata.self_link
                o.save(update_fields=["backend_handle"])

    def delete_record(self, o):
        secret = self.get_secret(o)
        if not secret:
            log.info("Kubernetes secret does not exist; Nothing to delete.", o=o)
            return
        delete_options = self.kubernetes_client.V1DeleteOptions()
        self.v1core.delete_namespaced_secret(o.name, o.trust_domain.name, delete_options)
        log.info("Deleted secret from kubernetes", handle=o.backend_handle)
