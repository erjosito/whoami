# Sample containers

This repository contains two sample containers to test microservices applications in Docker and Kubernetes:

* sql api
* web

Note that the images are pretty large, since they are based on standard ubuntu and centos distros. The goal is having a fully functional OS in case any in-container troubleshooting or investigation is required.

The labs described below include how to deploy these containers in different form factors:

* [Lab 1: Docker running locally](#lab1)
* [Lab 2: Azure Container Instances with public IP addresses](#lab2)
* [Lab 3: Azure Container Instances with private IP addresses](#lab3)
* [Lab 4: Pods in an Azure Kubernetes Services cluster](#lab4)
* [Lab 5: Azure Web Application with public IP addresses](#lab5)
  * [Lab 5.1: Azure Web Application with Vnet integration (NOT AVAILABLE YET)](#lab5.1)
  * [Lab 5.2: Azure Web App with private link for frontend (NOT AVAILABLE YET)](#lab5.2)

## SQL API

sql-api (available in docker hub in [here](https://hub.docker.com/repository/docker/erjosito/sqlapi)), it offers the following endpoints:

* `/healthcheck`: returns a basic JSON code
* `/sql`: returns the results of a SQL query (`SELECT @@VERSION`) against a SQL database
* `/ip`: returns IP information

Environment variables can be also injected via files in the `/secrets` directory:

* `SQL_SERVER_FQDN`: FQDN of the SQL server
* `SQL_SERVER_USERNAME`: username for the SQL server
* `SQL_SERVER_PASSWORD`: password for the SQL server

## Web

Simple PHP web page that can access the previous API.

Environment variables:

* `API_URL`: URL where the SQL API can be found

## Lab 1: Docker running locally<a name="lab1"></a>

Start locally a SQL Server container:

```shell
password="yoursupersecretpassword"
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=$password" -p 1433:1433 --name sql1 -d mcr.microsoft.com/mssql/server:2019-GA-ubuntu-16.04
```

Now you can start the SQL API container and refer it to the SQL server (assuming here that the SQL server container got the 172.17.0.2 IP address), and start the Web container and refer it to the SQL API (assuming here the SQL container got the 172.17.0.3 IP address). If you dont know which IP address the container got, you can find it out with `docker inspect sql1`:

```shell
docker run -d -p 8080:8080 -e SQL_SERVER_FQDN=172.17.0.2 -e SQL_SERVER_USERNAME=sa -e SQL_SERVER_PASSWORD=$password --name sqlapi sqlapi:0.1
docker run -d -p 8081:80 -e API_URL=http://172.17.0.3:8080 --name web erjosito/whoami:0.1
```

## Lab 2: Azure Container Instances (public IP addresses)<a name="lab2"></a>

Create an Azure SQL database:

```shell
# Resource Group
rg=containerlab
location=westeurope
az group create -n $rg -l $location
# SQL Server and Database
sql_server_name=myserver$RANDOM
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
```

Create an Azure Container Instance with the API:

```shell
# Create ACI for API
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=$sql_server_fqdn" --image erjosito/sqlapi:0.1 --ip-address public --ports 8080
```

You can verify that the api has access to the SQL server. Before, we need to add the egress IP for the API container to the firewall rules in the SQL Server. We will use the `ip` endpoint of the API container, that gives us its egress public IP address (besides other details):

```shell
# SQL Server firewall rules
sqlapi_ip=$(az container show -n api -g $rg --query ipAddress.ip -o tsv)
sqlapi_source_ip=$(curl -s http://${sqlapi_ip}:8080/ip | jq -r .my_public_ip)
az sql server firewall-rule create -g $rg -s $sql_server_name -n sqlapi-source --start-ip-address $sqlapi_source_ip --end-ip-address $sqlapi_source_ip
curl http://${sqlapi_ip}:8080/healthcheck
curl http://${sqlapi_ip}:8080/sql
```

Finally, you can deploy the web frontend to a new ACI:

```shell
# Create ACI for web frontend
az container create -n web -g $rg -e "API_URL=http://${sqlapi_ip}:8080" --image erjosito/whoami:0.1 --ip-address public --ports 80
web_ip=$(az container show -n web -g $rg --query ipAddress.ip -o tsv)
echo "Please connect your browser to http://${web_ip} to test the correct deployment"
```

Notice how the Web frontend is able to reach the SQL database through the API.

## Lab 3: Azure Container Instances (in a Virtual Network)<a name="lab3"></a>

Create an Azure SQL database:

We will start creating an Azure database, as in the previous lab:

```shell
# Resource Group
rg=containerlab
location=westeurope
az group create -n $rg -l $location
# SQL Server and database
sql_server_name=myserver$RANDOM
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
```

We need a Virtual Network. We will create two subnets, one for the containers and the other to connect the database (over [Azure Private Link](https://azure.microsoft.com/services/private-link/)):

```shell
# Virtual Network
vnet_name=myvnet
vnet_prefix=192.168.0.0/16
subnet_aci_name=aci
subnet_aci_prefix=192.168.1.0/24
subnet_sql_name=sql
subnet_sql_prefix=192.168.2.0/24
az network vnet create -g $rg -n $vnet_name --address-prefix $vnet_prefix -l $location
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_aci_name --address-prefix $subnet_aci_prefix
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_sql_name --address-prefix $subnet_sql_prefix
```

We can now create a private endpoint for our SQL Server in the subnet for the database:

```shell
# SQL Server private endpoint
endpoint_name=mysqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
```

We can have a look at the assigned IP address:

```shell
# Endpoint's private IP address
nic_id=$(az network private-endpoint show -n $endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "Private IP address for SQL server ${sql_server_name}: ${sql_endpoint_ip}"
nslookup ${sql_server_name}.privatelink.database.windows.net
```

Now we can create the Azure Container Instances in the vnet subnet, pointing to the private IP address (if you want to know why we are not using the FQDN, check out the next section on private DNS). We will use the vnet and subnet IDs (and not the vnet/subnet names) to avoid ambiguity:

```shell
# Create ACI for API
vnet_id=$(az network vnet show -n $vnet_name -g $rg --query id -o tsv)
subnet_aci_id=$(az network vnet subnet show -n $subnet_aci_name --vnet-name $vnet_name -g $rg --query id -o tsv)
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_endpoint_ip}" --image erjosito/sqlapi:0.1 --ip-address private --ports 8080 --vnet $vnet_id --subnet $subnet_aci_id
```

In order to test the setup, we will need a virtual machine in the same vnet:

```shell
# Create VM
subnet_vm_name=vm
subnet_vm_prefix=192.168.10.0/24
vm_name=testvm
vm_size=Standard_D2_v3
vm_pip_name=${vm_name}-pip
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_vm_name --address-prefix $subnet_vm_prefix
az vm create -n $vm_name -g $rg --vnet-name $vnet_name --subnet $subnet_vm_name --public-ip-address $vm_pip_name --generate-ssh-keys --image ubuntuLTS --priority Low --size $vm_size --no-wait
vm_pip=$(az network public-ip show  -g $rg -n $vm_pip_name --query ipAddress -o tsv)
```

Now we can run commands over the test VM to verify the container is working:

```shell
# Verify connectivity from the VM to the container
aci_sqlapi_ip=$(az container show -n api -g $rg --query 'ipAddress.ip' -o tsv)
echo "Azure Container instance assigned IP address ${aci_sqlapi_ip}. If this is not contained in the subnet ${subnet_aci_prefix} you might want to recreate the container"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/healthcheck"
```

If the container was not created with the proper IP, you can just recreate it:

```shell
# Redeploy ACI
az container delete -n api -g $rg -y
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_endpoint_ip}" --image erjosito/sqlapi:0.1 --ip-address private --ports 8080 --vnet $vnet_id --subnet $subnet_aci_id
```

We need to include the private iP address of the container in the SQL Server firewall rules:

```shell
# Add Firewall rule (is this required????)
az sql server firewall-rule create -g $rg -s $sql_server_name -n aci-sqlapi-source --start-ip-address $aci_sqlapi_ip --end-ip-address $aci_sqlapi_ip
```

And we can verify connectivity to the SQL database:

```shell
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/sql"
```

Now we can create a web frontend that connects to the API container. We will give it a private IP address too, otherwise it would not be able to connect to the API. In order to test the correct deployment, you could use the VM as jump host:

```shell
# Create ACI for Web frontend
az container create -n web -g $rg -e "API_URL=http://${aci_sqlapi_ip}" --image erjosito/whoami:0.1 --ip-address public --ports 80  --vnet $vnet_id --subnet $subnet_aci_id
aci_web_ip=$(az container show -n web -g $rg --query 'ipAddress.ip' -o tsv)
ssh $vm_pip "curl -s http://${aci_web_ip}/healthcheck"
ssh $vm_pip "curl -s http://${aci_web_ip}"
```

### Lab 3.1 - Azure DNS and ACI not working together yet<a name="lab3.1"></a>

At this point in time, name resolution using Azure DNS private zones does not work. We can optionally use a private DNS zone for name resolution, and create a recordset in out private zone:

```shell
# Create Azure DNS private zone and records
dns_zone_name=privatelink.database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg 
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled true
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $sql_endpoint_ip
```

Note that the DNS private zone is linked with auto-registration enabled. We will try two things: first, we will verify whether the SQL container can resolve a the A record we have just created. We will create the ACI with SQL_SERVER_FQDN pointing to that record:

```shell
# Recreate ACI with new settings
az container delete -n api -g $rg -y
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_server_name}.privatelink.database.windows.net" --image erjosito/sqlapi:0.1 --ip-address private --ports 8080 --vnet $vnet_name --subnet $subnet_aci_name
```

Now you can verify with the `ip` endpoint of the API whether the container is resolving the SQL server's FQDN to the public or the private IP address:

```shell
sqlapi_ip=$(az container show -n api -g $rg --query 'ipAddress.ip' -o tsv)
ssh $pip "curl -s http://${sqlapi_ip}:8080/ip"
```

Here you can see a sample output showing the resolution to the public IP (`40.68.37.158` in the sample output below). In other words, ACI are not leveraging Azure DNS private zones:

```console
$ ssh $pip "curl -s http://${sqlapi_ip}:8080/ip"
{
  "my_private_ip": "192.168.1.5",
  "my_public_ip": "23.97.230.229",
  "path_accessed": "192.168.1.5:8080/ip",
  "sql_server_fqdn": "myserver14591.privatelink.database.windows.net",
  "sql_server_ip": "40.68.37.158",
  "x-forwarded-for": null,
  "your_address": "192.168.10.4",
  "your_browser": "None",
  "your_platform": "None"
}
```

We could further investigate in the container how naming resolution is configured:

```shell
# Verify DNS resolution
az container exec -n api -g $rg "nslookup ${sql_server_name}.privatelink.database.windows.net"
```

Secondly, we will check whether whether auto-registration works as well for Azure Container Instances. If it worked, you should see a new record-set for the container. Otherwise, you will only see the A record we created manually for the SQL server, the record created automatically for the test VM (which verifies that auto-registration is working) plus the default `@` SOA record:

```shell
az network private-dns record-set list -z $dns_zone_name -g $rg -o table
```

Here you can see a sample output showing that auto-registration for ACI is not working:

```console
# Verify records created in the private zone
$ az network private-dns record-set list -z $dns_zone_name -g $rg -o table
Name           ResourceGroup    Ttl    Type    AutoRegistered    Metadata
-------------  ---------------  -----  ------  ----------------  ----------
@              containerlab     3600   SOA     False
myserver14591  containerlab     3600   A       False
testvm         containerlab     10     A       True
```

If you want to remove the DNS link from the vnet for troubleshooting purposes, you can use this command:

```shell
# Remove private link
az network private-dns link vnet delete -g $rg -z $dns_zone_name -n myDnsLink -y
```

## Lab 4. AKS cluster in a Virtual Network<a name="lab4"></a>

For this lab we will use Azure Kubernetes Service (AKS). The first thing we need is a cluster. We will deploy an AKS cluster in our own vnet, so we will create the vnet first. We will create the SQL private endpoint as in lab 3 as well:

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
endpoint_name=mysqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
nic_id=$(az network private-endpoint show -n $endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "The SQL Server is reachable over the private IP address ${sql_endpoint_ip}"
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
kubectl -n $ns1_name run sqlapi --image=erjosito/sqlapi:0.1 --replicas=2 --env="SQL_SERVER_USERNAME=$sql_username" --env="SQL_SERVER_PASSWORD=$sql_password" --env="SQL_SERVER_FQDN=${sql_endpoint_ip}" --port=8080
kubectl -n $ns1_name expose deploy/sqlapi --name=sqlapi --port=8080 --type=LoadBalancer
```

Now we can verify whether the API is working (note that AKS will need 30-60 seconds to provision a public IP for the Kubernetes service, so the following commands might not work at the first attempt):

```shell
# Get API service public IP
aks_sqlapi_ip=$(kubectl -n $ns1_name get svc/sqlapi -o json | jq -rc '.status.loadBalancer.ingress[0].ip' 2>/dev/null)
curl "http://${aks_sqlapi_ip}:8080/healthcheck"
```

And you can find out some details about how networking is configured inside of the pod:

```shell
curl "http://${aks_sqlapi_ip}:8080/ip"
```

We do not need to update the firewall rules in the firewall to accept connections from the SQL API, since we are using the private IP endpoint to access it. Still, commands provided as a reference, if you decided to use the public endpoint for the SQL server:

```shell
# SQL Server Firewall rules
# aks_sqlapi_source_ip=$(curl -s "http://${aks_sqlapi_ip}:8080/ip" | jq -r '.my_public_ip')
# az sql server firewall-rule create -g $rg -s $sql_server_name -n sqlapi-source --start-ip-address $aks_sqlapi_source_ip --end-ip-address $aks_sqlapi_source_ip
```

And verify whether connectivity to the SQL server is working:

```shell
curl "http://${aks_sqlapi_ip}:8080/sql"
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

### Lab 4.1: protect the AKS cluster with network policies - WORK IN PROGRESS

As our AKS cluster stands, anybody can connect to both the web frontend and the API pods. In Kubernetes you can use Network Policies to restrict ingress or egress connectivity for a container. Sample network policies are provided in this repository, in the [k8s](k8s) directory.

In order to test access a Virtual Machine inside of the Virtual Network will be useful. Let's kick off the creation of one:

```shell
# Create VM for testing purposes
subnet_vm_name=vm
subnet_vm_prefix=192.168.10.0/24
vm_name=testvm
vm_size=Standard_D2_v3
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
aks_sqlapi_source_ip=$(curl -s http://${aks_sqlapi_ip}:8080/ip | jq -r .my_public_ip)
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
ssh $vm_pip "curl -s http://${pod_ip}:8080/healthcheck"
# Verify outbound connectivity
# pod_id=$(kubectl -n $ns2_name get pod -l run=sqlapi -o json | jq -r '.items[0].metadata.name')
# kubectl -n $ns2_name exec -it $pod_id -- curl ifconfig.co
curl -s "http://${aks_sqlapi_ip}:8080/sql"
```

Our first action will be denying all network communication, and verifying:

```shell
# Deny all traffic to/from API pods
base_url="https://raw.githubusercontent.com/erjosito/whoami/master/k8s"
kubectl -n $ns2_name apply -f "${base_url}/netpol-sqlapi-deny-all.yaml"
# Verify inbound connectivity (it should NOT work and timeout, feel free to Ctrl-C the operation)
ssh $vm_pip "curl -s http://${pod_ip}:8080/healthcheck"
# Verify outbound connectivity (it should NOT work and timeout, feel free to Ctrl-C the operation)
# kubectl -n $ns2_name exec -it $pod_id -- curl ifconfig.co
curl -s "http://${aks_sqlapi_ip}:8080/sql"
```

Now you can add a second policy that will allow egress communication to the SQL Server public IP address, we can verify whether it is working:

```shell
# Allow traffic to the SQL Server public IP address
sql_server_pip=$(nslookup ${sql_server_fqdn} | awk '/^Address: / { print $2 }')
curl -s "${base_url}/netpol-sqlapi-allow-egress-oneipvariable.yaml" | awk '{sub(/{{ip_address}}/,"'$sql_server_pip'")}1' | kubectl -n $ns2_name apply -f -
# Verify inbound connectivity (it should NOT work and timeout, feel free to Ctrl-C the operation)
ssh $vm_pip "curl -s http://${pod_ip}:8080/healthcheck"
# Verify outbound connectivity (it should now work)
# kubectl -n $ns2_name exec -it $pod_id -- curl ifconfig.co
curl -s "http://${aks_sqlapi_ip}:8080/sql"
```

```shell
# Allow egress traffic from API pods
kubectl apply -f "${base_url}/netpol-sqlapi-allow-egress-all.yaml"
pod_id=$(kubectl get pod -l run=sqlapi -o json | jq -r '.items[0].metadata.name')
# Verify inbound connectivity
ssh $vm_pip "curl http://${pod_ip}:8080/healthcheck"
# Verify outbound connectivity
kubectl exec -it $pod_id -- ping 8.8.8.8
```

If you need to connect to one of the AKS nodes for troubleshooting, here is how to do it, if the public SSH keys of the VM and the AKS cluster were set correctly:

```shell
# SSH to AKS nodes
aks_node_ip=$(kubectl get node -o wide -o json | jq -r '.items[0].status.addresses[] | select(.type=="InternalIP") | .address')
ssh -J $vm_pip $aks_node_ip
```

### Lab 4.2: further exercises<a name="lab4.2"></a>

Kubernetes in general is a functionality-technology. You can extend this lab by incorporating multiple concepts, here some examples (the list is not exhaustive by far):

* Ingress controller: configure an ingress controller to offer a common public IP address for both the web frontend and the API backend 
* Pod identity and Azure Key Vault integration: inject the SQL password in the SQL API pod as a file injected from Key Vault, and not as an environment variable
* Use a service mesh to provide TLS encryption in the connectivity between containers
* Install Prometheus to measure metrics such as Requests per Second and configure alerts
* Configure an Horizontal Pod Autoscaler to auto-scale the API as more requests are sent

## Lab 5: Azure App Services for Linux<a name="lab5"></a>

For this lab we will use Azure Application Services for Linux. Let us create a resource group and a SQL Server:

```shell
# Resource group
rg=containerlab
location=westeurope
sql_server_name=myserver$RANDOM
az group create -n $rg -l $location
# Azure SQL
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password --no-wait
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
```

Now we can create an App Service Plan, and a Web App referencing the API image:

```shell
# Create Web App for API
svcplan_name=webappplan
app_name_api=api-$RANDOM
app_name_web=web-$RANDOM
az appservice plan create -n $svcplan_name -g $rg --sku B1 --is-linux
az webapp create -n $app_name_api -g $rg -p $svcplan_name --deployment-container-image-name erjosito/sqlapi:0.1
az webapp config appsettings set -n $app_name_api -g $rg --settings "WEBSITES_PORT=8080" "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_server_fqdn}"
az webapp restart -n $app_name_api -g $rg
app_url_api=$(az webapp show -n $app_name_api -g $rg --query defaultHostName -o tsv)
curl "http://${app_url_api}/healthcheck"
```

As usual, we need to add the outbound public IP of the Web App to the firewall rules of the SQL Server, and verify that SQL access is working properly:

```shell
# SQL Server firewall rules
sqlapi_webapp_source_ip=$(curl -s http://${app_url_api}/ip | jq -r .my_public_ip)
az sql server firewall-rule create -g $rg -s $sql_server_name -n webapp-sqlapi-source --start-ip-address $sqlapi_webapp_source_ip --end-ip-address $sqlapi_webapp_source_ip
az sql server firewall-rule list -g $rg -s $sql_server_name -o table
curl -s "http://${app_url_api}/sql"
```

Now we can deploy a second app in our service plan with the web component:

```shell
# Create Web App for web frontend
az webapp create -n $app_name_web -g $rg -p $svcplan_name --deployment-container-image-name erjosito/whoami:0.1
az webapp config appsettings set -n $app_name_web -g $rg --settings "API_URL=http://${app_url_api}"
az webapp restart -n $app_name_web -g $rg
app_url_web=$(az webapp show -n $app_name_web -g $rg --query defaultHostName -o tsv)
echo "You can point your browser to http://${app_url_web} to verify the front end"
```

### Lab 5.1. Azure App Services with Vnet integration and private link: backend - NOT AVAILABLE YET<a name="lab5.1"></a>

This lab is built on top of the previous one, you will need to have deployed the Web App and the SQL server before proceeding here (see the instructions in the previous section). Once you do that, we can integrate the Web App and the SQL Server in the Vnet. Let's start by creating the vnet with two subnets:

```shell
# Virtual Network
vnet_name=myvnet
vnet_prefix=192.168.0.0/16
subnet_webapp_be_name=webapp-be
subnet_webapp_be_prefix=192.168.5.0/24
subnet_sql_name=sql
subnet_sql_prefix=192.168.2.0/24
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_webapp_be_name --address-prefix $subnet_webapp_be_prefix
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_sql_name --address-prefix $subnet_sql_prefix
```

We can start with the private endpoint for the SQL database, since we have already seen in previous labs how to do that:

```shell
# SQL private endpoint
endpoint_name=mysqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
nic_id=$(az network private-endpoint show -n $endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
```

Before moving on, let's make a note on the egress public IP that the Web App is using to reach out to the Internet:

```shell
old_webapp_source_ip=$(curl -s http://${app_url_api}:8080/ip | jq -r .my_public_ip)
echo "Before vnet integration, the egress IP address for the web app is ${old_webapp_source_ip}"
```

Now we can integrate the Web App with the vnet, and verify that the web app has a new outbound public IP:

```shell
# Vnet integration
az webapp vnet-integration add -n $app_name_api -g $rg --vnet $vnet_name --subnet-name $subnet_webapp_be_name
new_webapp_source_ip=$(curl -s http://${app_url_api}:8080/ip | jq -r .my_public_ip)
echo "After vnet integration, the egress IP address for the web app is ${new_webapp_source_ip}"
```

Now we can instruct the web app to reach the SQL Server on the private IP address:

```shell
# Modify API settings
az webapp config appsettings set -n $app_name_api -g $rg --settings "SQL_SERVER_FQDN=${sql_endpoint_ip}"
az webapp restart -n $app_name_api -g $rg
```

We can now verify whether the web app has the new setting, and whether connectivity to the SQL server is working:

```shell
curl "http://${app_url_api}:8080/ip"
curl "http://${app_url_api}:8080/sql"
```

### Lab 5.2. Azure App Services with Vnet integration and private link: frontend - NOT AVAILABLE YET<a name="lab5.2"></a>

We can integrate the frontend of the webapp in our vnet as well, so that it is accessible only from within the vnet or from on-premises. In order to test this, we will need a VM inside the virtual network:

```shell
# Create VM for testing purposes
subnet_vm_name=vm
subnet_vm_prefix=192.168.10.0/24
vm_name=testvm
vm_size=Standard_D2_v3
vm_pip_name=${vm_name}-pip
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_vm_name --address-prefix $subnet_vm_prefix
az vm create -n $vm_name -g $rg --vnet-name $vnet_name --subnet $subnet_vm_name --public-ip-address $vm_pip_name --generate-ssh-keys --image ubuntuLTS --priority Low --size $vm_size --no-wait
vm_pip=$(az network public-ip show  -g $rg -n $vm_pip_name --query ipAddress -o tsv)
```

Now we can create a private endpoint for our web app:

```shell
# Webapp private endpoint
subnet_webapp_fe_name=webapp-be
subnet_webapp_fe_prefix=192.168.6.0/24
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_webapp_fe_name --address-prefix $subnet_webapp_fe_prefix
webapp_endpoint_name=mywebep
svcplan_id=$(az appservice plan show -n $appsvc_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_webapp_fe_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $webapp_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_webapp_fe_name --private-connection-resource-id $svcplan_id --group-ids sqlServer --connection-name webappConnection
webapp_nic_id=$(az network private-endpoint show -n $endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
webapp_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
```

From our Virtual Machine we should now be able to reach the Web App on its private IP:

```shell
# Reach the web app's private IP
ssh $vm_pip "curl -s http://${webapp_endpoint_ip}:8080/healthcheck"
```

The last step would be configure the web frontend to use the API private endpoint:

```shell
# Vnet integration for the web frontend
az webapp vnet-integration add -n $app_name_web -g $rg --vnet $vnet_name --subnet-name $subnet_webapp_be_name
az webapp config appsettings set -n $app_name_web -g $rg --settings "API_URL=http://${webapp_endpoint_ip}"
az webapp restart -n $app_name_web -g $rg
echo "You can point your browser to http://${app_url_web} to verify the web front end"
```