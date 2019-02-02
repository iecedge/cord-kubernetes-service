
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
    sync_service.py

    Synchronize Services. The only type of Service this step knows how to deal with are services that use Kubernetes
    NodePort to expose ports.
"""

from xossynchronizer.steps.syncstep import SyncStep
from xossynchronizer.modelaccessor import Service

from xosconfig import Config
from multistructlog import create_logger

log = create_logger(Config().get('logging'))

class SyncService(SyncStep):

    """
        SyncService

        Implements sync step for syncing Services.
    """

    provides = [Service]
    observes = Service
    requested_interval = 0

    def __init__(self, *args, **kwargs):
        super(SyncService, self).__init__(*args, **kwargs)
        self.init_kubernetes_client()

    def init_kubernetes_client(self):
        from kubernetes.client.rest import ApiException
        from kubernetes import client as kubernetes_client, config as kubernetes_config
        kubernetes_config.load_incluster_config()
        self.kubernetes_client = kubernetes_client
        self.v1core = kubernetes_client.CoreV1Api()
        self.ApiException = ApiException

    def fetch_pending(self, deletion=False):
        """ Filter the set of pending objects.
            As this syncstep can only create Service that exist within Trust Domains, filter out those services that
            don't have Trust Domains associated with them.
        """
        models = super(SyncService, self).fetch_pending(deletion)

        if (not deletion):
            for model in models[:]:
                if not self.get_trust_domain(model):
                    # If this happens, then either the Service has no Slices, or it does have slices but none of
                    # those slices are associated with a TrustDomain. Assume the developer has done this on purpose
                    # and ignore the Service.
                    log.debug("Unable to determine Trust Domain for service %s. Ignoring." % model.name)
                    models.remove(model)
                elif not model.serviceports.exists():
                    # If there are not ServicePorts, then there's not much for us to do at this time...
                    log.debug("Service %s has no serviceports. Ignoring." % model.name)
                    models.remove(model)

        return models

    def get_trust_domain(self, o):
        """ Given a service, determine its Trust Domain.

            The design we've chosen to go with is that a service is pinned to a Trust Domain based on the slices
            that it contains. It's an error for a service to be directly comprised of slices from multiple
            trust domains.

            This allows for "logical services", that contain no slices of their own, but are comprised of multiple
            subservices. For example, EPC.
        """

        trust_domain = None
        for slice in o.slices.all():
            if slice.trust_domain:
                if (trust_domain is None):
                    trust_domain = slice.trust_domain
                elif (trust_domain.id != slice.trust_domain.id):
                    # Bail out of we've encountered a situation where a service spans multiple trust domains.
                    log.warning("Service %s is comprised of slices from multiple trust domains." % o.name)
                    return None

        return trust_domain

    def get_service(self, o, trust_domain_name):
        """ Given an XOS Service, read the associated Service from Kubernetes.
            If no Kubernetes service exists, return None
        """
        try:
            k8s_service = self.v1core.read_namespaced_service(o.name, trust_domain_name)
        except self.ApiException, e:
            if e.status == 404:
                return None
            raise
        return k8s_service

    def sync_record(self, o):
        trust_domain = self.get_trust_domain(o)
        k8s_service = self.get_service(o,trust_domain.name)

        if not k8s_service:
            k8s_service = self.kubernetes_client.V1Service()
            k8s_service.metadata = self.kubernetes_client.V1ObjectMeta(name=o.name)

            ports=[]
            for service_port in o.serviceports.all():
                port=self.kubernetes_client.V1ServicePort(name = service_port.name,
                                                  node_port = service_port.external_port,
                                                  port = service_port.internal_port,
                                                  target_port = service_port.internal_port,
                                                  protocol = service_port.protocol)
                ports.append(port)

            k8s_service.spec = self.kubernetes_client.V1ServiceSpec(ports=ports,
                                                               type="NodePort")

            k8s_service = self.v1core.create_namespaced_service(trust_domain.name, k8s_service)

        if (not o.backend_handle):
            o.backend_handle = k8s_service.metadata.self_link
            o.save(update_fields=["backend_handle"])

    def delete_record(self, o):
        trust_domain_name = None
        trust_domain = self.get_trust_domain(o)
        if trust_domain:
            trust_domain_name = trust_domain.name
        else:
            # rely on backend_handle being structured like this one,
            #     /api/v1/namespaces/service1-trust/services/service1
            if (o.backend_handle):
                parts = o.backend_handle.split("/")
                if len(parts)>3:
                    trust_domain_name = parts[-3]

        if not trust_domain_name:
            raise Exception("Can't delete service %s because there is no trust domain" % o.name)

        k8s_service = self.get_service(o, trust_domain_name)
        if not k8s_service:
            log.info("Kubernetes service does not exist; Nothing to delete.", o=o)
            return
        delete_options = self.kubernetes_client.V1DeleteOptions()
        self.v1core.delete_namespaced_service(o.name, trust_domain_name, delete_options)
        log.info("Deleted service from kubernetes", handle=o.backend_handle)
