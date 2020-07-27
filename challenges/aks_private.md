# Challenge: private AKS clusters

This challenge will cover deployment of AKS clusters fully integrated in a Virtual Network:

## Objectives

You need to fulfill these requirements to complete this challenge:

* Deploy an AKS cluster integrated in an existing VNet
* Make sure the Kubernetes API is reachable over a private IP address
* Deploy an Azure SQL Database and connect to it from the SQL API containers using a private IP address
* Deploy the SQL API and Web containers, expose them over an ingress controller
* Make sure the AKS cluster does not have **any** public IP address

## Related documentation

These docs might help you achieving these objectives:

* [Azure Private Link](https://docs.microsoft.com/azure/private-link/private-link-overview)
* [AKS Overview](https://docs.microsoft.com/azure/aks/)
