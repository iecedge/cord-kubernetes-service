# Kubernetes Service #

## Purpose ##

The Kubernetes Service is responsible for two tasks:
1. Monitoring Kubernetes for resources (primarily pods) that are created outside of XOS, and adding the state of those resources to the XOS data model.
2. Providing a mechanism for XOS services to create Kubernetes resources using the XOS data model.

The Kubernetes Service supports "joint management" of Kubernetes resources. Some resources are created outside of XOS, for example by Helm. Other resources may be created inside of XOS. All of these resources are inventoried and visible in the XOS data model, regardless of how they were created.

## Models ##

The following models are supported by the Kubernetes Service:

- `KubernetesService`. The KubernetesService model specifies the Kubernetes service that will be used. The system only supports one Kubernetes service at the moment, but it's expected that eventually multiple Kubernetes services may be used. This model serves as the root of the hierarchy of Kubernetes models -- each model is traceable back to a KubernetesService.
    - `name`. Name of the Kubernetes Service.
- `TrustDomain`. Trust domains logically group services and their resources together into a namespace where the resources can be found. A TrustDomain corresponds to a Kubernetes `namespace`.
    - `name`. Name of the trust domain
    - `owner`. The service that is partitioned by this trust domain. For Kubernetes trust domains, this will be an instance of the `KubernetesService` model.
- ```Principal```. Principals are entities that are able to perform operations on resources. A Principal corresponds to a Kubernetes `ServiceAccount`.
    - `name`. Name of this principal.
    - `trust_domain`. TrustDomain in which this principal resides.
- `Slice`. A Slice is a collection of compute resources and can also be thought of as a controller for those compute resources, implementing logic that creates and destroys the compute resources as necessary. This corresponds roughly to Kubernetes Controller objects. It's possible for a Slice to not have a corresponding Kubernetes controller, in which case it's assumed that an XOS service directly manages resources within the Slice, for example by use of an XOS model_policy.
    - `name`. Name of this Slice.
    - `site`. Site that this Slice belongs to, used for administrative accountability.
    - `trust_domain`. TrustDomain in which this slice resides.
    - `principal`. Principal that this can be used by this slice to operate on Kubernetes resources. Optional.
    - `controller_kind`. Type of controller.
    - `controller_replica_count`. For controllers that are able to manage replicas, a count of the desired number of replicas.
- `KubernetesServiceInstance`. This model corresponds directly to a Kubernetes pod.
    - `name`. Name of the pod.
    - `owner`. Service that owns this `ServiceInstance`, in this case, an instance of the `KubernetesService` model. 
    - `slice`. Relation to the `Slice` that manages this pod.
    - `image`. Relation to the `Image` that is used by this pod.
    - `pod_ip`. IP address assigned by Kubernetes. Read-only.
- `KubernetesConfigMap`. This model corresponds directly to a Kubernetes ConfigMap. It stores a named set of (name, value) pairs.
    - `name`. Name of this ConfigMap.
    - `trust_domain`. TrustDomain in which this ConfigMap resides.
    - `data`. Json-encoded dictionary that contains (name, value) pairs.
- `KubernetesSecret`. This model corresponds directly to a Kubernetes Secret. It stores a named set of (name, value) pairs that are made available to pods in a secure manner.
    - `name`. Name of this Secret.
    - `trust_domain`. TrustDomain in which this Secret resides.
    - `data`. Json-encoded dictionary that contains (name, value) pairs.
- `KubernetesConfigVolumeMount`. This mounts a KubernetesConfigMap to a KubernetesServiceInstance.
    - `secret`. Relation to ConfigMap to be mounted.
    - `service_instance`. Relation to `KubernetesServiceInstance` where this ConfigMap will be mounted.
    - `mount_path`. Mountpoint within container filesystem.
    - `sub_path`. Subpath within ConfigMap to mount. Optional.
- `KubernetesSecretVolumeMount`. This mounts a KubernetesSecret to a KubernetesServiceInstance.
    - `secret`. Relation to Secret to be mounted.
    - `service_instance`. Relation to `KubernetesServiceInstance` where this Secret will be mounted.
    - `mount_path`. Mountpoint within container filesystem.
    - `sub_path`. Subpath within Secret to mount. Optional.
- `Service`. Services expose compute resources to other services and to the outside world, making them useful. Typically a Service contains one or more Slices.
    - `name`. Name of the service.
- `ServicePort`. ServicePort maps a port contained in the Service's pods to an external port that is visible on nodes. Currently this is implemented within the Kubernetes Service as a Kubernetes NodePort, though additional implementations (LoadBalancer, etc) will become available in the future.

## Pull Steps ##

The Kubernetes synchronizer implements a Pull Step that will look for externally-created pods and create objects in the XOS data model. The primary object created is `KubernetesServiceInstance`, with one of these objects created for each pod. Dependent objects will be created as necessary. For example, since the pod likely belongs to a Kubernetes controller, then a `Slice` will automatically be created. Since the `Slice` needs to be located within a `TrustDomain`, then a `TrustDomain` will automatically be created. 

## Creating Kubernetes Objects in XOS ##

An XOS Service can leverage the Kubernetes Service to creates Kubernetes resources on behalf of the XOS Service. An example of this is a `SimpleExampleService` service. To create a Kubernetes Service, it's suggested you create the following XOS Objects:

- `TrustDomain`
- `Slice`
- `Image`
- `KubernetesServiceInstance`
- `KubernetesConfigMap` and/or `KubernetesSecret`. Optional, if the pod requires configuration.
- `KubernetesConfigMapVolumeMount` and/or `KubernetesSecretVolumeMount`. Optional, if the pod requires configuration.

Here is a short example that implements that creates a pod:

```
# Create a new Trust Domain for the demo
t=TrustDomain(name="demo-trust", owner=KubernetesService.objects.first())
t.save()

# Use an existing image if one is available, otherwise create a new image.
existing_images=Image.objects.filter(name="k8s.gcr.io/pause-amd64")
if existing_images:
    img = existing_images[0]
else:
    img=Image(name="k8s.gcr.io/pause-amd64", tag="3.0")
    img.save()

# Create a new Slice for the demo
s=Slice(name="mysite_demo1", site=Site.objects.first(), trust_domain=t)
s.save()

# Create a KubernetesServiceInstance that will instantiate a pod
i=KubernetesServiceInstance(name="demo-pod", slice=s, image=img, owner=KubernetesService.objects.first(), xos_managed=True)
i.save()
```
