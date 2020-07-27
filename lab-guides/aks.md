# Azure Container Instances

In these lab guides you will go through setting up Azure Container Instances with some advanced networking features such as private link or the network policies. This guide contains the following labs:

* [Prerequisite: Create AKS cluster](#create)
* [Lab 1: Ingress Controller](#lab1)
* [Lab 2: Network Policies](#lab2)
* [Lab 3: AKS Private Cluster](#lab3)
* [Lab 4: Optional labs](#lab4)

## Prerequisite": AKS cluster in a Virtual Network<a name="create"></a>

For this lab we will use Azure Kubernetes Service (AKS). The first thing we need is a cluster. We will deploy an AKS cluster in our own vnet, so we will create the vnet first. We will create the SQL private endpoint as in lab 3 as well.

```shell
# Resource group
rg=containerlab
location=westeurope
sql_server_name=myserver$RANDOM
az group create -n $rg -l $location
# Vnet
vnet_name=myvnet
vnet_prefix=192.168.0.0/16
subnet_aks_name=aks
subnet_aks_prefix=192.168.3.0/24
subnet_sql_name=sql
subnet_sql_prefix=192.168.2.0/24
az network vnet create -g $rg -n $vnet_name --address-prefix $vnet_prefix -l $location
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_aks_name --address-prefix $subnet_aks_prefix
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_sql_name --address-prefix $subnet_sql_prefix
# AKS (Azure CNI plugin, Azure network policy)
aks_name=aks
aks_node_size=Standard_B2ms
aks_subnet_id=$(az network vnet subnet show -n $subnet_aks_name --vnet-name $vnet_name -g $rg --query id -o tsv)
az aks create -n $aks_name -g $rg -c 1 -s $aks_node_size --generate-ssh-keys --network-plugin azure --network-policy azure --vnet-subnet-id $aks_subnet_id --no-wait
# Azure SQL
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
# SQL Server private endpoint
sql_endpoint_name=sqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $sql_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
nic_id=$(az network private-endpoint show -n $sql_endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "The SQL Server is reachable over the private IP address ${sql_endpoint_ip}"
# Create Azure DNS private zone and records
dns_zone_name=privatelink.database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled false
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $sql_endpoint_ip
# Verify
az network private-dns link vnet list -g $rg -z $dns_zone_name -o table
```

Note that we deployed our AKS cluster with the `--no-wait` flag, verify that the deployment status is `Succeeded`:

```shell
# Verify that AKS cluster is created
az aks list -g $rg -o table
```

Once the AKS has been deployed successfully, you can start deploying the API containers as pods, as well as a service exposing the deployment:

```shell
# Deploy pods in namespace privatelink
az aks get-credentials -g $rg -n $aks_name --overwrite
ns1_name=privatelink
kubectl create namespace $ns1_name
kubectl -n $ns1_name run sqlapi --image=erjosito/sqlapi:0.1 --replicas=2 --env="SQL_SERVER_USERNAME=$sql_username" --env="SQL_SERVER_PASSWORD=$sql_password" --env="SQL_SERVER_FQDN=${sql_server_fqdn}" --port=8080
kubectl -n $ns1_name expose deploy/sqlapi --name=sqlapi --port=8080 --type=LoadBalancer
```

Now we can verify whether the API is working (note that AKS will need 30-60 seconds to provision a public IP for the Kubernetes service, so the following commands might not work at the first attempt. You can check the state of the service with `kubectl -n $ns1_name get svc`):

```shell
# Get API service public IP
aks_sqlapi_ip=$(kubectl -n $ns1_name get svc/sqlapi -o json | jq -rc '.status.loadBalancer.ingress[0].ip' 2>/dev/null)
curl "http://${aks_sqlapi_ip}:8080/api/healthcheck"
```

And you can find out some details about how networking is configured inside of the pod:

```shell
curl "http://${aks_sqlapi_ip}:8080/api/ip"
```

We can try to resolve the public DNS name of the SQL server, it should be resolved to the internal IP address. The reason is that coredns will forward per default to the DNS servers configured in the node (see [this article](https://kubernetes.io/docs/tasks/administer-cluster/dns-custom-nameservers/) for more details):

```shell
curl "http://${aks_sqlapi_ip}:8080/api/dns?fqdn=${sql_server_fqdn}"
```

We do not need to update the firewall rules in the firewall to accept connections from the SQL API, since we are using the private IP endpoint to access it. We can now verify whether connectivity to the SQL server is working:

```shell
# Verify 
curl "http://${aks_sqlapi_ip}:8080/api/sqlsrcip"
echo "The previous command should have given as source IP address one of the pods' IP addresses:"
kubectl -n $ns1_name get pod -o wide
```

Now we can deploy the web frontend pod. Note that as FQDN for the API pod we are using the name for the service:

```shell
# Deploy Web frontend pods
kubectl -n $ns1_name run sqlweb --image=erjosito/whoami:0.1 --replicas=2 --env="API_URL=http://sqlapi:8080" --port=80
kubectl -n $ns1_name expose deploy/sqlweb --name=sqlweb --port=80 --type=LoadBalancer
```

When the Web service gets a public IP address, you can connect to it over a Web browser:

```shell
# Get web frontend's public IP
aks_sqlweb_ip=$(kubectl -n $ns1_name get svc/sqlweb -o json | jq -rc '.status.loadBalancer.ingress[0].ip' 2>/dev/null)
echo "Point your web browser to http://${aks_sqlweb_ip}"
```

### Lab 1: Install an nginx ingress controller - WORK IN PROGRESS<a name="lab1"></a>

In this lab we will install our ingress controller in front of our two pods. We will not use the Application Gateway Ingress Controller, since it is not fully integrated in the AKS CLI yet, but the open source nginx. You can install an installation guide for nginx with helm [here[(https://docs.nginx.com/nginx-ingress-controller/installation/installation-with-helm/)]. For example, for helm3:

```shell
helm install my-release nginx-stable/nginx-ingress
```

### Lab 2: protect the AKS cluster with network policies - WORK IN PROGRESS<a name="lab2"></a>

As our AKS cluster stands, anybody can connect to both the web frontend and the API pods. In Kubernetes you can use Network Policies to restrict ingress or egress connectivity for a container. Sample network policies are provided in this repository, in the [k8s](k8s) directory.

In order to test access a Virtual Machine inside of the Virtual Network will be useful. Let's kick off the creation of one:

```shell
# Create VM for testing purposes
subnet_vm_name=vm
subnet_vm_prefix=192.168.10.0/24
vm_name=testvm
vm_size=Standard_D2_v3 # Since using spot, B-series doesnt support spot
vm_pip_name=${vm_name}-pip
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_vm_name --address-prefix $subnet_vm_prefix
az vm create -n $vm_name -g $rg --vnet-name $vnet_name --subnet $subnet_vm_name --public-ip-address $vm_pip_name --generate-ssh-keys --image ubuntuLTS --priority Low --size $vm_size --no-wait
```

We will create another app instance in a different namespace, that we will call `publicip`:

```shell
# Create namespace for app instance using the public IP of the SQL Server
ns2_name=publicip
kubectl create namespace $ns2_name
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
kubectl -n $ns2_name run sqlapi --image=erjosito/sqlapi:0.1 --replicas=2 --env="SQL_SERVER_USERNAME=$sql_username" --env="SQL_SERVER_PASSWORD=$sql_password" --env="SQL_SERVER_FQDN=${sql_server_fqdn}" --port=8080
kubectl -n $ns2_name expose deploy/sqlapi --name=sqlapi --port=8080 --type=LoadBalancer
kubectl -n $ns2_name run sqlweb --image=erjosito/whoami:0.1 --replicas=2 --env="API_URL=http://sqlapi:8080" --port=80
kubectl -n $ns2_name expose deploy/sqlweb --name=sqlweb --port=80 --type=LoadBalancer
```

We need to add the public IP to the SQL Server firewall rules:

```shell
# Add public IP to the Azure Firewall
aks_sqlapi_ip=$(kubectl -n $ns2_name get svc/sqlapi -o json | jq -rc '.status.loadBalancer.ingress[0].ip' 2>/dev/null)
aks_sqlapi_source_ip=$(curl -s http://${aks_sqlapi_ip}:8080/api/ip | jq -r .my_public_ip)
az sql server firewall-rule create -g $rg -s $sql_server_name -n aks-sqlapi-source --start-ip-address $aks_sqlapi_source_ip --end-ip-address $aks_sqlapi_source_ip
```

Let's verify that the new app instance is working:

```shell
# Get web frontend's public IP
aks_sqlweb_ip=$(kubectl -n $ns2_name get svc/sqlweb -o json | jq -rc '.status.loadBalancer.ingress[0].ip' 2>/dev/null)
echo "Point your web browser to http://${aks_sqlweb_ip}"
```

First, we will start by focusing on the API pods. Let's verify that this pod has inbound and outbound connectivity. For inbound connectivity we can access the pod from the test VM we created. For outbound we can just run a curl to the service `http://ifconfig.co`, which will return our public IP address (the value is not important, only that there is an answer at all):

```shell
# Verify inbound connectivity
vm_pip=$(az network public-ip show  -g $rg -n $vm_pip_name --query ipAddress -o tsv)
pod_ip=$(kubectl -n $ns2_name get pod -o wide -l run=sqlapi -o json | jq -r '.items[0].status.podIP')
ssh $vm_pip "curl -s http://${pod_ip}:8080/api/healthcheck"
# Verify outbound connectivity
# pod_id=$(kubectl -n $ns2_name get pod -l run=sqlapi -o json | jq -r '.items[0].metadata.name')
# kubectl -n $ns2_name exec -it $pod_id -- curl ifconfig.co
curl -s "http://${aks_sqlapi_ip}:8080/api/sql"
```

Our first action will be denying all network communication, and verifying:

```shell
# Deny all traffic to/from API pods
base_url="https://raw.githubusercontent.com/erjosito/whoami/master/k8s"
kubectl -n $ns2_name apply -f "${base_url}/netpol-sqlapi-deny-all.yaml"
# Verify inbound connectivity (it should NOT work and timeout, feel free to Ctrl-C the operation)
ssh $vm_pip "curl -s http://${pod_ip}:8080/api/healthcheck"
# Verify outbound connectivity (it should NOT work and timeout, feel free to Ctrl-C the operation)
# kubectl -n $ns2_name exec -it $pod_id -- curl ifconfig.co
curl -s "http://${aks_sqlapi_ip}:8080/api/sql"
```

Now you can add a second policy that will allow egress communication to the SQL Server public IP address, we can verify whether it is working:

```shell
# Allow traffic to the SQL Server public IP address
sql_server_pip=$(nslookup ${sql_server_fqdn} | awk '/^Address: / { print $2 }')
curl -s "${base_url}/netpol-sqlapi-allow-egress-oneipvariable.yaml" | awk '{sub(/{{ip_address}}/,"'$sql_server_pip'")}1' | kubectl -n $ns2_name apply -f -
# Verify inbound connectivity (it should NOT work and timeout, feel free to Ctrl-C the operation)
ssh $vm_pip "curl -s http://${pod_ip}:8080/api/healthcheck"
# Verify outbound connectivity (it should now work)
# kubectl -n $ns2_name exec -it $pod_id -- curl ifconfig.co
curl -s "http://${aks_sqlapi_ip}:8080/api/sql"
```

```shell
# Allow egress traffic from API pods
kubectl apply -f "${base_url}/netpol-sqlapi-allow-egress-all.yaml"
pod_id=$(kubectl get pod -l run=sqlapi -o json | jq -r '.items[0].metadata.name')
# Verify inbound connectivity
ssh $vm_pip "curl http://${pod_ip}:8080/api/healthcheck"
# Verify outbound connectivity
kubectl exec -it $pod_id -- ping 8.8.8.8
```

If you need to connect to one of the AKS nodes for troubleshooting, here is how to do it, if the public SSH keys of the VM and the AKS cluster were set correctly:

```shell
# SSH to AKS nodes
aks_node_ip=$(kubectl get node -o wide -o json | jq -r '.items[0].status.addresses[] | select(.type=="InternalIP") | .address')
ssh -J $vm_pip $aks_node_ip
```

### Lab 3: Private cluster and private link<a name="lab3"></a>

You can create an AKS cluster where the masters have a private IP with the flag `--enable-private-cluster`. Note that you might have to activate the features required for AKS private clusters (see [this link](https://docs.microsoft.com/azure/aks/private-clusters)):

```shell
# Create AKS cluster with private master endpoint
az aks create -n $aks_name -g $rg -c 1 -s $aks_node_size --generate-ssh-keys --network-plugin azure --network-policy azure --vnet-subnet-id $aks_subnet_id --enable-private-cluster --no-wait
```

When doing this, the master's IP will not be reachable from the public Internet, so unless you are connected to the vnet via VPN or ExpressRoute, you will have to run these execises from a Virtual Machine in the vnet. You can see the master's FQDN in the AKS cluster properties, and verify that it is not resolvable using global DNS:

```shell
# Find out FQDN of master
aks_master_fqdn=$(az aks show -n $aks_name -g $rg --query 'privateFqdn' -o tsv)
nslookup "$aks_master_fqdn"
```

However, it is resolvable from inside the virtual network, as we can verify with our test VM:

```shell
# Verify it is resolvable inside of the vnet
ssh $vm_pip "nslookup ${aks_master_fqdn}"
```

This works because the `az aks create` created a private DNS zone in the node resource group where the AKS resources are located:

```shell
# Find out node resource group name
node_rg=$(az aks show -n $aks_name -g $rg --query nodeResourceGroup -o tsv)
# List DNS zones in the node RG
az network private-dns zone list -g $node_rg -o table
# List recordsets in that DNS zone
aks_dnszone_name=$(az network private-dns zone list -g $node_rg --query '[0].name' -o tsv)
az network private-dns record-set list -z $aks_dnszone_name -g $node_rg -o table
```

Where does the private IP address of the AKS masters come from? It is a private endpoint deployed in the node resource group:

```shell
# Private endpoint for AKS master nodes in the node Resource Group
az network private-endpoint list -g $node_rg -o table
aks_endpoint_name=$(az network private-endpoint list -g $node_rg --query '[0].name' -o tsv)
aks_nic_id=$(az network private-endpoint show -n $aks_endpoint_name -g $node_rg --query 'networkInterfaces[0].id' -o tsv)
aks_endpoint_ip=$(az network nic show --ids $aks_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "The AKS masters are reachable over the IP ${aks_endpoint_ip}"
```

The only way to access the cluster is from inside the Virtual Network, so we will use the test VM for that:

```shell
# Install Az CLI and kubectl in the test VM
ssh $vm_pip 'curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash'
# kubectl
ssh $vm_pip 'sudo apt-get update && sudo apt-get install -y apt-transport-https'
ssh $vm_pip 'curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -'
ssh $vm_pip 'echo "deb https://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee -a /etc/apt/sources.list.d/kubernetes.list'
ssh $vm_pip 'sudo apt-get update'
ssh $vm_pip 'sudo apt-get install -y kubectl'
# Login and download AKS credentials
ssh $vm_pip 'az login'
ssh $vm_pip "az aks get-credentials -n ${aks_name} -g ${rg} --overwrite"
ssh $vm_pip 'kubectl get node -o wide'
```

### Lab 4: further exercises<a name="lab4"></a>

Kubernetes in general is a very rich functionality platform, and includes multiple network technologies. You can extend this lab by incorporating multiple concepts, here some examples (the list is not exhaustive by far):

* Ingress controller: configure an ingress controller to offer a common public IP address for both the web frontend and the API backend
* Pod identity and Azure Key Vault integration: inject the SQL password in the SQL API pod as a file injected from Key Vault, and not as an environment variable
* Use a service mesh to provide TLS encryption in the connectivity between containers
* Install Prometheus to measure metrics such as Requests per Second and configure alerts
* Configure an Horizontal Pod Autoscaler to auto-scale the API as more requests are sent
