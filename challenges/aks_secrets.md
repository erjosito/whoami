# AKS secret management

This challenge will cover the management of configuration and secrets in AKS:

## Objectives

You need to fulfill these requirements to complete this challenge:

* Supply environment variables to the Web and SQL API containers over Kubernetes config maps or secrets
* For critical secrets (like the database user password) make sure that they are not stored anywhere in the Kubernetes cluster, but in a purpose-built secret store such as Azure Key Vault
* The same goes for the ingress controller SSL certificate, it should be supplied into the ingress controller from a purpose-built store such as Azure Key Vault
* Make sure that no static password is store in the AKS cluster that allows access to the Azure Key Vault

## Related documentation

These docs might help you achieving these objectives:

* [Azure Key Vault](https://docs.microsoft.com/azure/key-vault/general/basic-concepts)
* [AKV provider for secrets store CSI driver](https://github.com/Azure/secrets-store-csi-driver-provider-azure)
* [AKS Overview](https://docs.microsoft.com/azure/aks/)
