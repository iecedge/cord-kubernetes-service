
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
     kubernetes-synchronizer.py

     This is the main entrypoint for the synchronizer. It loads the config file, and then starts the synchronizer.
"""

#!/usr/bin/env python

# Runs the standard XOS synchronizer

import importlib
import logging
import os
import sys
from xosconfig import Config

base_config_file = os.path.abspath(os.path.dirname(os.path.realpath(__file__)) + '/config.yaml')
mounted_config_file = os.path.abspath(os.path.dirname(os.path.realpath(__file__)) + '/mounted_config.yaml')

if os.path.isfile(mounted_config_file):
    Config.init(base_config_file, 'synchronizer-config-schema.yaml', mounted_config_file)
else:
    Config.init(base_config_file, 'synchronizer-config-schema.yaml')

from xoskafka import XOSKafkaProducer

# prevent logging noise from k8s API calls
logging.getLogger("kubernetes.client.rest").setLevel(logging.WARNING)

# init kafka producer connection
XOSKafkaProducer.init()

synchronizer_path = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "../../synchronizers/new_base")
sys.path.append(synchronizer_path)
mod = importlib.import_module("xos-synchronizer")
mod.main()

