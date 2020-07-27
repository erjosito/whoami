# AKS security

This challenge will cover the implementation of different security technologies in AKS.

## Objectives

You need to fulfill these requirements to complete this challenge:

* Make sure that the ingress controller is the only container that can communicate to the Web pods
* Make sure that no privileged containers can be started in the cluster
* Make sure that no LoadBalancer services can be created with a public IP address

## Related documentation

These docs might help you achieving these objectives:

* [Open Policy Agent](https://www.openpolicyagent.org/)
* [AKS Overview](https://docs.microsoft.com/azure/aks/)
