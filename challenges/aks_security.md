# AKS security

This challenge will cover the implementation of different security technologies in AKS.

## Objectives

You need to fulfill these requirements to complete this challenge:

* Make sure that the ingress controller is the only container that can communicate to the Web pods
* Make sure that no privileged containers can be started in the cluster
* Make sure that no LoadBalancer services with a public IP address can be created in the Kubernetes cluster

## Related documentation

These docs might help you achieving these objectives:

* [Open Policy Agent](https://www.openpolicyagent.org/)
* [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
* [AKS Overview](https://docs.microsoft.com/azure/aks/)
