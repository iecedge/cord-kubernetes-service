
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
    sync_trustdomain.py

    Synchronize TrustDomain. TrustDomains correspond roughly to Kubernetes namespaces.
"""

from xossynchronizer.steps.syncstep import SyncStep
from xossynchronizer.modelaccessor import TrustDomain

from xosconfig import Config
from multistructlog import create_logger

log = create_logger(Config().get('logging'))

class SyncTrustDomain(SyncStep):

    """
        SyncTrustsDomain

        Implements sync step for syncing trust domains.
    """

    provides = [TrustDomain]
    observes = TrustDomain
    requested_interval = 0

    def __init__(self, *args, **kwargs):
        super(SyncTrustDomain, self).__init__(*args, **kwargs)
        self.init_kubernetes_client()

    def init_kubernetes_client(self):
        from kubernetes.client.rest import ApiException
        from kubernetes import client as kubernetes_client, config as kubernetes_config
        kubernetes_config.load_incluster_config()
        self.kubernetes_client = kubernetes_client
        self.v1core = kubernetes_client.CoreV1Api()
        self.ApiException = ApiException

    def fetch_pending(self, deleted):
        """ Figure out which TrustDomains are interesting to the K8s synchronizer. It's necessary to filter as we're
            synchronizing a core model, and we only want to synchronize trust domains that will exist within
            Kubernetes.
        """
        objs = super(SyncTrustDomain, self).fetch_pending(deleted)
        for obj in objs[:]:
            # If the TrustDomain isn't part of the K8s service, then it's someone else's trust domain
            if "KubernetesService" not in obj.owner.leaf_model.class_names:
                objs.remove(obj)
        return objs

    def get_namespace(self, o):
        """ Give an XOS TrustDomain object, return the corresponding namespace from Kubernetes.
            Return None if no namespace exists.
        """
        try:
            ns = self.v1core.read_namespace(o.name)
        except self.ApiException, e:
            if e.status == 404:
                return None
            raise
        return ns

    def sync_record(self, o):
            ns = self.get_namespace(o)
            if not ns:
                ns = self.kubernetes_client.V1Namespace()
                ns.metadata = self.kubernetes_client.V1ObjectMeta(name=o.name)

                log.info("creating namespace %s" % o.name)
                ns=self.v1core.create_namespace(ns)

            if (not o.backend_handle):
                o.backend_handle = ns.metadata.self_link
                o.save(update_fields=["backend_handle"])

    def delete_record(self, o):
        namespace = self.get_namespace(o)
        if not namespace:
            log.info("Kubernetes trust domain does not exist; Nothing to delete.", o=o)
            return
        delete_options = self.kubernetes_client.V1DeleteOptions()
        self.v1core.delete_namespace(o.name, delete_options)
        log.info("Deleted trust domain from kubernetes", handle=o.backend_handle)

