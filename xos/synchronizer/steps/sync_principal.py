
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
    sync_principal.py

    Synchronize Principals. Principals correspond roughly to Kubernetes ServiceAccounts.
"""

from xossynchronizer.steps.syncstep import SyncStep
from xossynchronizer.modelaccessor import Principal

from xosconfig import Config
from multistructlog import create_logger

log = create_logger(Config().get('logging'))

class SyncPrincipal(SyncStep):

    """
        SyncPrincipal

        Implements sync step for syncing Principals.
    """

    provides = [Principal]
    observes = Principal
    requested_interval = 0

    def __init__(self, *args, **kwargs):
        super(SyncPrincipal, self).__init__(*args, **kwargs)
        self.init_kubernetes_client()

    def init_kubernetes_client(self):
        from kubernetes.client.rest import ApiException
        from kubernetes import client as kubernetes_client, config as kubernetes_config
        kubernetes_config.load_incluster_config()
        self.kubernetes_client = kubernetes_client
        self.v1core = kubernetes_client.CoreV1Api()
        self.ApiException = ApiException

    def get_service_account(self, o):
        """ Given an XOS Principal object, read the corresponding ServiceAccount from Kubernetes.
            return None if no ServiceAccount exists.
        """
        try:
            service_account = self.v1core.read_namespaced_service_account(o.name, o.trust_domain.name)
        except self.ApiException, e:
            if e.status == 404:
                return None
            raise
        return service_account

    def fetch_pending(self, deleted):
        """ Figure out which Principals are interesting to the K8s synchronizer.
            As each Principal exists within a Trust Domain, this reduces to figuring out which Trust Domains are
            interesting.
        """
        objs = super(SyncPrincipal, self).fetch_pending(deleted)
        for obj in objs[:]:
            # If the Principal isn't in a TrustDomain, then the K8s synchronizer can't do anything with it
            if not obj.trust_domain:
                objs.remove(obj)
                continue

            # If the Principal's TrustDomain isn't part of the K8s service, then it's someone else's principal
            if "KubernetesService" not in obj.trust_domain.owner.leaf_model.class_names:
                objs.remove(obj)
        return objs

    def sync_record(self, o):
            service_account = self.get_service_account(o)
            if not service_account:
                service_account = self.kubernetes_client.V1ServiceAccount()
                service_account.metadata = self.kubernetes_client.V1ObjectMeta(name=o.name)

                service_account = self.v1core.create_namespaced_service_account(o.trust_domain.name, service_account)

            if (not o.backend_handle):
                o.backend_handle = service_account.metadata.self_link
                o.save(update_fields=["backend_handle"])

    def delete_record(self, o):
        principal = self.get_service_account(o)
        if not principal:
            log.info("Kubernetes service account does not exist; Nothing to delete.", o=o)
            return
        delete_options = self.kubernetes_client.V1DeleteOptions()
        self.v1core.delete_namespaced_service_account(o.name, o.trust_domain.name, delete_options)
        log.info("Deleted Principal from kubernetes", handle=o.backend_handle)
