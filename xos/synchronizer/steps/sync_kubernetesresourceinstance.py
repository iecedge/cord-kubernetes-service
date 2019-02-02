
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
    sync_kubernetesresourceinstance.py

    Synchronize KubernetesResourceInstance.

    This sync_step is instantiates generic resources by executing them with `kubectl`.
"""

import os
import subprocess
import tempfile
from xossynchronizer.steps.syncstep import SyncStep
from xossynchronizer.modelaccessor import KubernetesResourceInstance

from xosconfig import Config
from multistructlog import create_logger

log = create_logger(Config().get('logging'))

class SyncKubernetesResourceInstance(SyncStep):

    """
        SyncKubernetesResourceInstance

        Implements sync step for syncing kubernetes resource instances. These objects are basically a yaml blob that
        is passed to `kubectl`.
    """

    provides = [KubernetesResourceInstance]
    observes = KubernetesResourceInstance
    requested_interval = 0

    def __init__(self, *args, **kwargs):
        super(SyncKubernetesResourceInstance, self).__init__(*args, **kwargs)

    def run_kubectl(self, operation, recipe):
        (tmpfile, fn)=tempfile.mkstemp()
        os.write(tmpfile, recipe)
        os.close(tmpfile)
        try:
            p = subprocess.Popen(args=["/usr/local/bin/kubectl", operation, "-f", fn],
                                 stdin=None,
                                 stderr=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 close_fds=True)
            (stdout, stderr) = p.communicate()
            log.info("kubectl completed", stderr=stderr, stdout=stdout, recipe=recipe)
            if p.returncode!=0:
                raise Exception("Process failed with returncode %s" % p.returncode)
        finally:
            os.remove(fn)

    def sync_record(self, o):
        self.run_kubectl("apply", o.resource_definition)
        if (o.kubectl_state == "created"):
            o.kubectl_state = "updated"
        else:
            o.kubectl_state = "created"
        o.save(update_fields=["kubectl_state"])

    def delete_record(self, o):
        if o.kubectl_state in ["created", "updated"]:
            self.run_kubectl("delete", o.resource_definition)
            o.kubectl_state="deleted"
            o.save(update_fields=["kubectl_state"])
