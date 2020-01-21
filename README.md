# Container and Web App networking

This repository contains two sample containers to test microservices applications in Docker and Kubernetes:

* sql api
* web

Note that the images are pretty large, since they are based on standard ubuntu and centos distros. The goal is having a fully functional OS in case any in-container troubleshooting or investigation is required.

The labs described below include how to deploy these containers in different form factors:

* [Lab 1: Docker running locally](#lab1)
* [Lab 2: Azure Container Instances with public IP addresses](#lab2)
  * [Lab 2.2: Azure Container Instances with public IP addresses and MySQL](#lab2.2)
* [Lab 3: Azure Container Instances with private IP addresses](#lab3)
* [Lab 4: Pods in an Azure Kubernetes Services cluster](#lab4)
* [Lab 5: Azure Linux Web App with public IP addresses](#lab5)
  * [Lab 5.1: Azure Linux Web Application with Vnet integration](#lab5.1)
  * [Lab 5.2: Azure Linux Web App with private link for frontend (NOT AVAILABLE YET)](#lab5.2)
* [Lab 6: Azure Windows Web App](#lab6)


## SQL API

sql-api (available in docker hub in [here](https://hub.docker.com/repository/docker/erjosito/sqlapi)), it offers the following endpoints:

* `/healthcheck`: returns a basic JSON code
* `/sqlversion`: returns the results of a SQL query (`SELECT @@VERSION`) against a SQL database. You can override the value of the `SQL_SERVER_FQDN` via a query parameter 
* `/sqlsrcip`: returns the results of a SQL query (`SELECT CONNECTIONPROPERTY("client_net_address")`) against a SQL database. You can override the value of the `SQL_SERVER_FQDN` via a query parameter
* `/ip`: returns information about the IP configuration of the container, such as private IP address, egress public IP address, default gateway, DNS servers, etc
* `/dns`: returns the IP address resolved from the FQDN supplied in the parameter `fqdn`
* `/printenv`: returns the environment variables for the container
* `/curl`: returns the output of a curl request, you can specify the argument with the parameter `url`
* `/mysql`: queries a MySQL database. It uses the same environment variables as the SQL Server endpoints, and you can override them with query parameters

Environment variables can be also injected via files in the `/secrets` directory:

* `SQL_SERVER_FQDN`: FQDN of the SQL server
* `SQL_SERVER_DB` (optional): FQDN of the SQL server
* `SQL_SERVER_USERNAME`: username for the SQL server
* `SQL_SERVER_PASSWORD`: password for the SQL server
* `PORT` (optional): TCP port where the web server will be listening (8080 per default)

## Web

Simple PHP web page that can access the previous API.

Environment variables:

* `API_URL`: URL where the SQL API can be found, for example `http://1.2.3.4:8080`

## Lab 1: Docker running locally<a name="lab1"></a>

Start locally a SQL Server container:

```shell
# Run database
sql_password="yoursupersecretpassword"
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=$sql_password" -p 1433:1433 --name sql -d mcr.microsoft.com/mssql/server:2019-GA-ubuntu-16.04
```

Now you can start the SQL API container and refer it to the SQL server (assuming here that the SQL server container got the 172.17.0.2 IP address), and start the Web container and refer it to the SQL API (assuming here the SQL container got the 172.17.0.3 IP address). If you dont know which IP address the container got, you can find it out with `docker inspect sql1` (and yes, you can install `jq` on Windows with [chocolatey](https://chocolatey.org/)):

```shell
# Run API container
sql_ip=$(docker inspect sql | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
docker run -d -p 8080:8080 -e "SQL_SERVER_FQDN=$sql_ip" -e "SQL_USERNAME=sa" -e "SQL_PASSWORD=$sql_password" --name api erjosito/sqlapi:0.1
```

Now you can start the web interface, and refer to the IP address of the API (which you can find out from the `docker inspect` command)

```shell
# Run Web frontend
api_ip=$(docker inspect api | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
docker run -d -p 8081:80 -e "API_URL=http://${api_api}:8080" --name web erjosito/whoami:0.1
# web_ip=$(docker inspect web | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
echo "You can point your browser to http://127.0.0.1:8081 to verify the app"
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
public_aci_name=publicapi
az container create -n $public_aci_name -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=$sql_server_fqdn" --image erjosito/sqlapi:0.1 --ip-address public --ports 8080
```

You can verify that the api has access to the SQL server. Before, we need to add the egress IP for the API container to the firewall rules in the SQL Server. We will use the `ip` endpoint of the API container, that gives us its egress public IP address (besides other details):

```shell
# SQL Server firewall rules
sqlapi_ip=$(az container show -n $public_aci_name -g $rg --query ipAddress.ip -o tsv)
sqlapi_source_ip=$(curl -s http://${sqlapi_ip}:8080/ip | jq -r .my_public_ip)
az sql server firewall-rule create -g $rg -s $sql_server_name -n public_sqlapi_aci-source --start-ip-address $sqlapi_source_ip --end-ip-address $sqlapi_source_ip
curl "http://${sqlapi_ip}:8080/healthcheck"
curl "http://${sqlapi_ip}:8080/sqlsrcip"
echo "The output of the previous command should have been $sqlapi_source_ip"
```

Finally, you can deploy the web frontend to a new ACI:

```shell
# Create ACI for web frontend
az container create -n web -g $rg -e "API_URL=http://${sqlapi_ip}:8080" --image erjosito/whoami:0.1 --ip-address public --ports 80
web_ip=$(az container show -n web -g $rg --query ipAddress.ip -o tsv)
echo "Please connect your browser to http://${web_ip} to test the correct deployment"
```

Notice how the Web frontend is able to reach the SQL database through the API.

### Lab 2.2: Azure Container Instances with Azure MySQL<a name="lab2.2"></a>

Let's start with creating a MySQL server and a database:

```shell
# Create mysql server
mysql_name=mysql$RANDOM
mysql_db_name=mydb
mysql_sku=B_Gen5_1
az mysql server create -g $rg -n $mysql_name -u $sql_username -p $sql_password --sku-name $mysql_sku --ssl-enforcement Disabled
az mysql db create -g $rg -s $mysql_name -n $mysql_db_name
mysql_fqdn=$(az mysql server show -n $mysql_name -g $rg -o tsv --query fullyQualifiedDomainName)
```

We can open the firewall rules for our previously deployed Azure Container Instance:

```shell
# Open firewall rules
sqlapi_ip=$(az container show -n $public_aci_name -g $rg --query ipAddress.ip -o tsv)
sqlapi_source_ip=$(curl -s http://${sqlapi_ip}:8080/ip | jq -r .my_public_ip)
az mysql server firewall-rule create -g $rg -s $mysql_name -n public_sqlapi_aci-source --start-ip-address $sqlapi_source_ip --end-ip-address $sqlapi_source_ip
```

Now we can try to access from our previous Azure Container Instance. We will override the environment variable using the query parameters, since it was configured to point to the Azure SQL Database (and not to our Azure Database for MySQL):

```shell
# Test access to the mysql server
curl "http://${sqlapi_ip}:8080/mysql?SQL_SERVER_FQDN=${mysql_fqdn}"   # Not WORKING YET!!!
```

## Lab 3: Azure Container Instances in a Virtual Network (NOT WORKING YET))<a name="lab3"></a>

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
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_endpoint_fqdn}" --image erjosito/sqlapi:0.1 --ip-address private --ports 8080 --vnet $vnet_id --subnet $subnet_aci_id --no-wait
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

Verify that the VM and the container are successfully created:

```shell
# Verify VM status
az vm list -g $rg -o table
# Verify ACI status
az container list -g $rg -o table
```

Now we can run commands over the test VM to verify the container is working (you will have to accept the prompt to validate the authencity of the VM host over SSH):

```shell
# Verify connectivity from the VM to the container
aci_sqlapi_ip=$(az container show -n api -g $rg --query 'ipAddress.ip' -o tsv)
echo "Azure Container instance assigned IP address ${aci_sqlapi_ip}. If this is not contained in the subnet ${subnet_aci_prefix} you might want to recreate the container"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/healthcheck"
```

In the case the container was not created with the proper IP in the correct range (`192.168.1.0/24` in this lab), you can just recreate it:

```shell
# Redeploy ACI if (ONLY if needed)
az container delete -n api -g $rg -y
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_server_fqdn}" --image erjosito/sqlapi:0.1 --ip-address private --ports 8080 --vnet $vnet_id --subnet $subnet_aci_id
aci_sqlapi_ip=$(az container show -n api -g $rg --query 'ipAddress.ip' -o tsv)
echo "Azure Container instance assigned IP address ${aci_sqlapi_ip}. If this is not contained in the subnet ${subnet_aci_prefix} you might want to recreate the container"
```

We can verify the IP settings of the container, and the resolution of the SQL Server FQDN:

```shell
# Verify ACI's environment variables IP configuration and DNS resolution
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/printenv"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/ip"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/dns?fqdn=${sql_server_fqdn}"
```

As you can see, the container's DNS server is the Vnet's DNS server, however DNS resolution is not working correctly and it is mapping the SQL Server FQDN to its public IP address, and not to the private one. Let's deploy an Azure DNS private zone:

```shell
# Create Azure DNS private zone and records
dns_zone_name=database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg 
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled false
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $sql_endpoint_ip
```

We can verify that the private DNS zone is working using our test VM:

```shell
# Verify DNS private zones working correctly
ssh $vm_pip "nslookup ${sql_server_fqdn}"
```

As you can see, DNS private zones seem to be broken, but we can hack our way in using the `/etc/hosts` file (probably not a good idea if you are thinking about putting this in production):

```shell
# Hacking the SQL Server FQDN in the hosts file, since private zones do not seem to work with ACI containers
cmd="echo \"${sql_endpoint_ip} ${sql_server_fqdn}\" >>/etc/hosts"
echo "Please run this command in the container console:"
echo $cmd
az container exec -n api -g $rg --exec-command /bin/bash
# az container exec -n api -g $rg --exec-command $cmd # Does not work for some reason
```

And we can verify connectivity to the SQL database:

```shell
# Verify DNS resolution and SQL Server connectivity
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/dns?fqdn=${sql_server_fqdn}"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/sqlsrcip"
```

**Still not working!**

Now we can create a web frontend that connects to the API container. We will give it a private IP address too, otherwise it would not be able to connect to the API. In order to test the correct deployment, you could use the VM as jump host:

```shell
# Create ACI for Web frontend
az container create -n web -g $rg -e "API_URL=http://${aci_sqlapi_ip}" --image erjosito/whoami:0.1 --ip-address public --ports 80  --vnet $vnet_id --subnet $subnet_aci_id
aci_web_ip=$(az container show -n web -g $rg --query 'ipAddress.ip' -o tsv)
ssh $vm_pip "curl -s http://${aci_web_ip}/healthcheck"
ssh $vm_pip "curl -s http://${aci_web_ip}"
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
# Create Azure DNS private zone and records
dns_zone_name=database.windows.net
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
curl "http://${aks_sqlapi_ip}:8080/healthcheck"
```

And you can find out some details about how networking is configured inside of the pod:

```shell
curl "http://${aks_sqlapi_ip}:8080/ip"
```

We can try to resolve the public DNS name of the SQL server, it should be resolved to the internal IP address. The reason is that coredns will forward per default to the DNS servers configured in the node (see [this article](https://kubernetes.io/docs/tasks/administer-cluster/dns-custom-nameservers/) for more details):

```shell
curl "http://${aks_sqlapi_ip}:8080/dns?fqdn=${sql_server_fqdn}"
```

We do not need to update the firewall rules in the firewall to accept connections from the SQL API, since we are using the private IP endpoint to access it. We can now verify whether connectivity to the SQL server is working:

```shell
# Verify 
curl "http://${aks_sqlapi_ip}:8080/sqlsrcip"
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

### Lab 5.1. Azure App Services with Vnet integration and private link<a name="lab5.1"></a>

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

## Lab 6. Azure Windows Web App Services with Vnet integration and private link:<a name="lab6"></a>

We can run a similar test with Windows-based Azure web apps. First we well deploy some basic infrastructure, if you are starting from scratch:

```shell
# Resource group
rg=containerlab
location=westeurope
az group create -n $rg -l $location
# Azure SQL
sql_server_name=myserver$RANDOM
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
# Optionally test for serverless SKU
# az sql db update -g $rg -s $sql_server_name -n $sql_db_name --edition GeneralPurpose --min-capacity 1 --capacity 4 --family Gen5 --compute-model Serverless --auto-pause-delay 1440
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
# Create Vnet
vnet_name=myvnet
vnet_prefix=192.168.0.0/16
subnet_sql_name=sql
subnet_sql_prefix=192.168.2.0/24
subnet_webapp_be_name=webapp-be
subnet_webapp_be_prefix=192.168.5.0/24
az network vnet create -g $rg -n $vnet_name --address-prefix $vnet_prefix -l $location
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_sql_name --address-prefix $subnet_sql_prefix
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_webapp_be_name --address-prefix $subnet_webapp_be_prefix
# Create Windows Web App for API
svcplan_name=webappplan
app_name_api=api-$RANDOM
az appservice plan create -n $svcplan_name -g $rg --sku B1
# Update svc plan if required
az appservice plan update -n $svcplan_name -g $rg --sku S1
# Create web app (see `az webapp list-runtimes` for the runtimes)
az webapp create -n $app_name_api -g $rg -p $svcplan_name  -r "aspnet|V4.7"
app_url_api=$(az webapp show -n $app_name_api -g $rg --query defaultHostName -o tsv)
echo "Web app url is https://${app_url_api}"
```

Integrating the web app in the vnet is just one command:

```shell
# Create vnet integration
az webapp vnet-integration add -n $app_name_api -g $rg --vnet $vnet_name --subnet $subnet_webapp_be_name
# Verify
az webapp vnet-integration list -n $app_name_api -g $rg -o table
```

We will now load the great app by [Jelle Druyts](https://github.com/jelledruyts/), a simple aspx file with the possibility of doing interactive tests (similar to the sqlapi container used in previous labs):

```shell
# load app
app_file_url=https://raw.githubusercontent.com/jelledruyts/Playground/master/web/default.aspx
app_file_name=default.aspx
wget $app_file_url -O $app_file_name
creds=($(az webapp deployment list-publishing-profiles -n $app_name_api -g $rg --query "[?contains(publishMethod, 'FTP')].[publishUrl,userName,userPWD]" --output tsv))
# curl -T $app_file_name -u ${creds[1]}:${creds[2]} ${creds[0]}/
curl -T $app_file_name -u ${creds[2]}:${creds[3]} ${creds[1]}/
echo "Check out this URL: http://${app_url_api}/${app_file_name}"
```

We should update the SQL Server firewall rules with the egress IP addresses of the firewall. In this lab we will just open up the firewall to all IP addresses, but in a production setup you would only allow the actual outbound IP addresses of the web app, that you can get with the command `az webapp show` (see below for the full syntax):

```shell
# Update Firewall
# az webapp show -n api-26567 -g $rg --query outboundIpAddresses
# Creating one rule for each outbound IP: not implemented yet. Workaround: fully open
az sql server firewall-rule create -g $rg -s $sql_server_name -n permitAny --start-ip-address "0.0.0.0" --end-ip-address "255.255.255.255"
az sql server firewall-rule list -g $rg -s $sql_server_name -o table
```

We can use the Azure CLI to get the connection string for the database:

```shell
# Get connection string
db_client_type=ado.net
az sql db show-connection-string -n $sql_db_name -s $sql_server_name -c $db_client_type -o tsv | awk '{sub(/<username>/,"'$sql_username'")}1' | awk '{sub(/<password>/,"'$sql_password'")}1'
```

At this point you should be able to send Query over the web app GUI with `SELECT CONNECTIONPROPERTY('client_net_address')` and the previous connection string. This query should work, since it is going over the public IP at this time.

Let's now create a private endpoint for our SQL Server:

```shell
# Create SQL private endpoint (note that there is no integration with private DNS from the CLI)
endpoint_name=mysqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
# Get private endpoint ip
nic_id=$(az network private-endpoint show -n $endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "Private IP address for SQL server ${sql_server_name}: ${sql_endpoint_ip}"
```

We can use Azure DNS private zones to provide DNS resolution for our web app, and create an A record that maps the SQL server FQDN to the private IP address:

```shell
# Create Azure DNS private zone and records: database.windows.net
dns_zone_name=database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg 
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled false
# Create record (private dns zone integration not working in the CLI)
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $sql_endpoint_ip
# Verification: list recordsets in the zone
az network private-dns record-set list -z $dns_zone_name -g $rg -o table
az network private-dns record-set a show -n $sql_server_name -z $dns_zone_name -g $rg --query aRecords -o table
```

We will need a DNS server living in a VM, since at this point in time the web app cannot address the native DNS functionality of a vnet (this will probably change in the future). A web server will be installed in the VM as well, for troubleshooting purposes:

```shell
# Create DNS server VM
subnet_dns_name=dns-vm
subnet_dns_prefix=192.168.53.0/24
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_dns_name --address-prefix $subnet_dns_prefix
dnsserver_name=dnsserver
dnsserver_pip_name=dns-vm-pip
dnsserver_size=Standard_D2_v3
az vm create -n $dnsserver_name -g $rg --vnet-name $vnet_name --subnet $subnet_dns_name --public-ip-address $dnsserver_pip_name --generate-ssh-keys --image ubuntuLTS --priority Low --size $dnsserver_size --no-wait
dnsserver_ip=$(az network public-ip show -n $dnsserver_pip_name -g $rg --query ipAddress -o tsv)
dnsserver_nic_id=$(az vm show -n $dnsserver_name -g $rg --query 'networkProfile.networkInterfaces[0].id' -o tsv)
dnsserver_privateip=$(az network nic show --ids $dnsserver_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "DNS server deployed to $dnsserver_privateip, $dnsserver_ip"
echo "IP configuration of the VM:"
ssh $dnsserver_ip "ip a"
ssh $dnsserver_ip "sudo apt -y install apache2 dnsmasq"
```

There are two options to force the web app to use the DNS server. The first one is configuring our DNS server as the default for the whole vnet. Bouncing the vnet integration (deleting and recreating) might be required so that the web app takes the changes:

```shell
# Configure web app for DNS - Option 1:
# DNS server as server for the vnet (required only if not setting the app setting)
az network vnet update -n $vnet_name -g $g --dns-servers $dnsserver_privateip
# Bounce the vnet integration to take the new DNS config
az webapp vnet-integration delete -n $app_name_api -g $rg 
az webapp vnet-integration add -n $app_name_api -g $rg --vnet $vnet_name --subnet $subnet_webapp_be_name
```

The second option consists in instructing the web app to use the DNS server in the VM that we just deployed. The benefit of this option is that other VMs in the vnet will not be affected.

```shell
# Configure web app for DNS - Option 2:
# Change web app DNS settings (https://www.azuretechguy.com/how-to-change-the-dns-server-in-azure-app-service)
az webapp config appsettings set -n $app_name_api -g $rg --settings "WEBSITE_DNS_SERVER=${dnsserver_privateip}
az webapp restart -n $app_name_api -g $rg
```

Now you can send the SQL uery over the app to `SELECT CONNECTIONPROPERTY('client_net_address')`, it should be using the private IP address

## Cleanup

Do not forget to `az group delete -n $rg -y --no-wait`!
