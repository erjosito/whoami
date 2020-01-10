# Sample containers

This repository contains two sample containers to test microservices applications in Docker and Kubernetes:

* sql api
* web

Note that the images are pretty large, since they are based on standard ubuntu and centos distros. The goal is having a fully functional OS in case any in-container troubleshooting or investigation is required.

The labs described below include how to deploy these containers in different form factors:

* Azure Container Instances with public IP addresses
* Azure Container Instances with private IP addresses
* Pods in an Azure Kubernetes Services cluster
* Azure Web Application with public IP addresses
* Azure Web Application with Vnet integration

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

## Lab 1: Docker running locally

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

## Lab 2: Azure Container Instances (public IP addresses)

Create an Azure SQL database:

```shell
rg=acitest
location=westeurope
sql_server_name=myserver$RANDOM
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az group create -n $rg -l $location
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
```

Create an Azure Container Instance with the API:

```shell
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=$sql_server_fqdn" --image erjosito/sqlapi:0.1 --ip-address public --ports 8080
```

You can verify that the api has access to the SQL server. Before, we need to add the egress IP for the API container to the firewall rules in the SQL Server. We will use the `ip` endpoint of the API container, that gives us its egress public IP address (besides other details):

```shell
sqlapi_ip=$(az container show -n api -g $rg --query ipAddress.ip -o tsv)
sqlapi_source_ip=$(curl -s http://${sqlapi_ip}:8080/ip | jq -r .my_public_ip)
az sql server firewall-rule create -g $rg -s $sql_server_name -n sqlapi-source --start-ip-address $sqlapi_source_ip --end-ip-address $sqlapi_source_ip
curl http://${sqlapi_ip}:8080/healthcheck
curl http://${sqlapi_ip}:8080/sql
```

Finally, you can deploy the web frontend to a new ACI:

```shell
az container create -n web -g $rg -e "API_URL=http://${sqlapi_ip}:8080" --image erjosito/whoami:0.1 --ip-address public --ports 80
web_ip=$(az container show -n web -g $rg --query ipAddress.ip -o tsv)
echo "Please connect your browser to http://${web_ip} to test the correct deployment"
```

Notice how the Web frontend is able to reach the SQL database through the API.

## Lab 3: Azure Container Instances (in a Virtual Network)

Create an Azure SQL database:

We will start creating an Azure database, as in the previous lab:

```shell
rg=acitest
location=westeurope
sql_server_name=myserver$RANDOM
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az group create -n $rg -l $location
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
```

We need a Virtual Network. We will create two subnets, one for the containers and the other to connect the database (over [Azure Private Link](https://azure.microsoft.com/services/private-link/)):

```shell
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
endpoint_name=mysqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
```

We can have a look at the assigned IP address:

```shell
nic_id=$(az network private-endpoint show -n $endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "Private IP address for SQL server ${sql_server_name}: ${endpoint_ip}"
nslookup ${sql_server_name}.privatelink.database.windows.net
```

Now we can create the Azure Container Instances in the vnet subnet, pointing to the private IP address (if you want to know why we are not using the FQDN, check out the next section on private DNS). We will use the vnet and subnet IDs (and not the names) to avoid ambiguity:

```shell
vnet_id=$(az network vnet show -n $vnet_name -g $rg --query id -o tsv)
subnet_aci_id=$(az network vnet subnet show -n $subnet_aci_name --vnet-name $vnet_name -g $rg --query id -o tsv)
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${endpoint_ip}" --image erjosito/sqlapi:0.1 --ip-address private --ports 8080 --vnet $vnet_id --subnet $subnet_aci_id
```

In order to test the setup, we will need a virtual machine in the same vnet:

```shell
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
aci_sqlapi_ip=$(az container show -n api -g $rg --query 'ipAddress.ip' -o tsv)
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/healthcheck"
```

We need to include the private iP address of the container in the SQL Server firewall rules:

```shell
az sql server firewall-rule create -g $rg -s $sql_server_name -n aci-sqlapi-source --start-ip-address $aci_sqlapi_ip --end-ip-address $aci_sqlapi_ip
```

And we can verify connectivity to the SQL database:

```shell
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/sql"
```


**to do: deploy web container**

### Lab 3 Appendix - Azure DNS and ACI not working together yet

At this point in time, name resolution using Azure DNS private zones does not work. We can optionally use a private DNS zone for name resolution, and create a recordset in out private zone:

```shell
dns_zone_name=privatelink.database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg 
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled true
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $endpoint_ip
```

Note that the DNS private zone is linked with auto-registration enabled. We will try two things: first, we will verify whether the SQL container can resolve a the A record we have just created. We will create the ACI with SQL_SERVER_FQDN pointing to that record:

```shell
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
az container exec -n api -g $rg "nslookup ${sql_server_name}.privatelink.database.windows.net"
```

Secondly, we will check whether whether auto-registration works as well for Azure Container Instances. If it worked, you should see a new record-set for the container. Otherwise, you will only see the A record we created manually for the SQL server, the record created automatically for the test VM (which verifies that auto-registration is working) plus the default `@` SOA record:

```shell
az network private-dns record-set list -z $dns_zone_name -g $rg -o table
```

Here you can see a sample output showing that auto-registration for ACI is not working:

```shell
Name           ResourceGroup    Ttl    Type    AutoRegistered    Metadata
-------------  ---------------  -----  ------  ----------------  ----------
@              acitest          3600   SOA     False
myserver14591  acitest          3600   A       False
testvm         acitest          10     A       True
```

If you want to remove the DNS link from the vnet, you can use this command:

```shell
az network private-dns link vnet delete -g $rg -z $dns_zone_name -n myDnsLink -y
```

## Lab 4. Kubernetes (in a Virtual Network)

For this lab we will use Azure Kubernetes Service. The first thing we need is a cluster. We will deploy an AKS cluster in our own vnet, so we will create the vnet first. We will create the SQL private endpoint as in lab 3 as well:

```shell
# Resource group
rg=akstest
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
# AKS
aks_name=aks
aks_node_size=Standard_B2ms
aks_subnet_id=$(az network vnet subnet show -n $subnet_aks_name --vnet-name $vnet_name -g $rg --query id -o tsv)
az aks create -n $aks_name -g $rg -c 1 -s $aks_node_size --generate-ssh-keys --vnet-subnet-id $aks_subnet_id --no-wait
# Azure SQL
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
sql_server_fqdn=$(az sql server show -n $sql_server_name -g $rg -o tsv --query fullyQualifiedDomainName)
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
# Azure private endpoint
endpoint_name=mysqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
nic_id=$(az network private-endpoint show -n $endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
```

Note that we deployed our AKS cluster with the `--no-wait` flag, verify that the deployment status is `Succeeded`:

```shell
az aks list -g $rg -o table
```

Once the AKS has been deployed successfully, you can start deploying the API containers as pods, as well as a service exposing the deployment:

```shell
az aks get-credentials -g $rg -n $aks_name --overwrite
kubectl run sqlapi --image=erjosito/sqlapi:0.1 --replicas=2 --env="SQL_SERVER_USERNAME=$sql_username" --env="SQL_SERVER_PASSWORD=$sql_password" --env="SQL_SERVER_FQDN=${endpoint_ip}" --port=8080
kubectl expose deploy/sqlapi --name=sqlapi --port=8080 --type=LoadBalancer
```

Now we can verify whether the API is working (note that AKS will need 30-60 seconds to provision a public IP for the Kubernetes service, so the following commands might not work at the first attempt):

```shell
sqlapi_ip=$(kubectl get svc/sqlapi -o json | jq -rc '.status.loadBalancer.ingress[0].ip' 2>/dev/null)
curl "http://${sqlapi_ip}:8080/healthcheck"
```

And you can find out some details about how networking is configured inside of the pod:

```shell
curl "http://${sqlapi_ip}:8080/ip"
```

We do not need to update the firewall rules in the firewall to accept connections from the SQL API, since we are using the private IP endpoint to access it. Still, commands provided as a reference, if you decided to use the public endpoint for the SQL server:

```shell
# sqlapi_source_ip=$(curl -s "http://${sqlapi_ip}:8080/ip" | jq -r '.my_public_ip')
# az sql server firewall-rule create -g $rg -s $sql_server_name -n sqlapi-source --start-ip-address $sqlapi_source_ip --end-ip-address $sqlapi_source_ip
```

And verify whether connectivity to the SQL server is working:

```shell
curl "http://${sqlapi_ip}:8080/sql"
```

Now we can deploy the web frontend pod. Not that as FQDN for the API pod we are using the name for the service:

```shell
kubectl run sqlweb --image=erjosito/whoami:0.1 --replicas=2 --env="API_URL=http://sqlapi:8080" --port=80
kubectl expose deploy/sqlweb --name=sqlweb --port=80 --type=LoadBalancer
```

When the Web service gets a public IP address, you can connect to it over a Web browser:

```shell
sqlweb_ip=$(kubectl get svc/sqlweb -o json | jq -rc '.status.loadBalancer.ingress[0].ip' 2>/dev/null)
echo "Point your web browser to http://${sqlweb_ip}"
```

## Lab 5: Azure App Services (public IP addresses)

For this lab we will use Azure Application Services for Linux. Let us create a resource group and a SQL Server:

```shell
# Resource group
rg=webapptest
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
# Web App
svcplan_name=webappplan
app_name_api=api-$RANDOM
app_name_web=web-$RANDOM
az appservice plan create -n $svcplan_name -g $rg --sku B1 --is-linux
az webapp create -n $app_name_api -g $rg -p $svcplan_name --deployment-container-image-name erjosito/sqlapi:0.1
az webapp config appsettings set -n $app_name_api -g $rg --settings "WEBSITES_PORT=8080" "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_server_fqdn}"
az webapp restart -n $app_name_api -g $rg
app_url_api=$(az webapp show -n $app_name_api -g $rg --query defaultHostName -o tsv)
curl "http://${app_url_api}:8080/healthcheck"
```

## Lab 6. Azure App Services (Vnet integration)