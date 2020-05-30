# Container and Web App networking

This repository contains two sample containers to test microservices applications in Docker and Kubernetes:

* sql api
* web

Note that the images are pretty large, since they are based on standard ubuntu and centos distros. The goal is having a fully functional OS in case any in-container troubleshooting or investigation is required.

The labs described below include how to deploy these containers in different form factors:

* [Lab 1: Docker running locally](#lab1)
* [Lab 2: Azure Container Instances with public IP addresses](#lab2)
  * [Lab 2.1: MySQL](#lab2.1)
  * [Lab 2.2: App Gateway](#lab2.2)
* [Lab 3: Azure Container Instances with private IP addresses](#lab3)
* [Lab 4: Pods in an Azure Kubernetes Services cluster](#lab4)
  * [Lab 4.1: Ingress Controller](#lab4.1)
  * [Lab 4.1: Network Policies](#lab4.2)
  * [Lab 4.1: AKS Private Cluster](#lab4.3)
  * [Lab 4.4: Optional labs](#lab4.4)
* [Lab 5: Azure Linux Web App](#lab5)
  * [Lab 5.1: Azure Linux Web Application with Vnet integration](#lab51)
  * [Lab 5.2: Azure Linux Web App with private link for frontend (NOT AVAILABLE YET)](#lab52)
* [Lab 6: Azure Windows Web App](#lab6)
* [Lab 7: Azure Virtual Machine](#lab7)


## SQL API

sql-api (available in docker hub in [here](https://hub.docker.com/repository/docker/erjosito/sqlapi)), it offers the following endpoints:

* `/api/healthcheck`: returns a basic JSON code
* `/api/sqlversion`: returns the results of a SQL query (`SELECT @@VERSION`) against a SQL database. You can override the value of the `SQL_SERVER_FQDN` via a query parameter 
* `/api/sqlsrcip`: returns the results of a SQL query (`SELECT CONNECTIONPROPERTY("client_net_address")`) against a SQL database. You can override the value of the `SQL_SERVER_FQDN` via a query parameter
* `/api/ip`: returns information about the IP configuration of the container, such as private IP address, egress public IP address, default gateway, DNS servers, etc
* `/api/dns`: returns the IP address resolved from the FQDN supplied in the parameter `fqdn`
* `/api/printenv`: returns the environment variables for the container
* `/api/curl`: returns the output of a curl request, you can specify the argument with the parameter `url`
* `/api/mysql`: queries a MySQL database. It uses the same environment variables as the SQL Server endpoints, and you can override them with query parameters

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

Following you have a list of labs. The commands are thought to be issued in a **Linux console**, but if you are running on a Powershell console they should work with some minor modifications (like adding a `$` in front of the variable names).

## Lab 1: Docker running locally<a name="lab1"></a>

Start locally a SQL Server container:

```shell
# Run database
sql_password="yoursupersecretpassword"  # Change this!
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=$sql_password" -p 1433:1433 --name sql -d mcr.microsoft.com/mssql/server:2019-GA-ubuntu-16.04
```

You can try some other interesting docker commands, like the following:

```shell
docker ps
docker stop
docker system prune
```

Now you can start the SQL API container and refer it to the SQL server (assuming here that the SQL server container got the 172.17.0.2 IP address), and start the Web container and refer it to the SQL API (assuming here the SQL container got the 172.17.0.3 IP address). If you dont know which IP address the container got, you can find it out with `docker inspect sql` (and yes, you can install `jq` on Windows with [chocolatey](https://chocolatey.org/), in case you are using docker under Windows):

```shell
# Run API container
sql_ip=$(docker inspect sql | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
docker run -d -p 8080:8080 -e "SQL_SERVER_FQDN=${sql_ip}" -e "SQL_SERVER_USERNAME=sa" -e "SQL_SERVER_PASSWORD=${sql_password}" --name api erjosito/sqlapi:0.1
```

Now you can start the web interface, and refer to the IP address of the API (which you can find out from the `docker inspect` command)

```shell
# Run Web frontend
api_ip=$(docker inspect api | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
docker run -d -p 8081:80 -e "API_URL=http://${api_api}:8080" --name web erjosito/whoami:0.1
# web_ip=$(docker inspect web | jq -r '.[0].NetworkSettings.Networks.bridge.IPAddress')
echo "You can point your browser to http://127.0.0.1:8081 to verify the app"
```

Please note that there are two links in the Web frontend that will only work if used with an ingress controller in Kubernetes (see the AKS sections further in this document).

## Lab 2: Azure Container Instances (public IP addresses)<a name="lab2"></a>

Create an Azure SQL database:

```shell
# Resource Group
rg=containerlab
location=westeurope
az group create -n $rg -l $location
# SQL Server and Database
sql_server_name=sqlserver$RANDOM
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
sqlapi_source_ip=$(curl -s http://${sqlapi_ip}:8080/api/ip | jq -r .my_public_ip)
az sql server firewall-rule create -g $rg -s $sql_server_name -n public_sqlapi_aci-source --start-ip-address $sqlapi_source_ip --end-ip-address $sqlapi_source_ip
curl "http://${sqlapi_ip}:8080/api/healthcheck"
curl "http://${sqlapi_ip}:8080/api/sqlsrcip"
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

### Lab 2.1: Azure Container Instances with Azure MySQL<a name="lab2.1"></a>

What has been tested so far is valid not only for Azure SQL Database (based on Microsoft SQL Server technology), but to the open source offerings such as Azure SQL Database for MySQL as well. Let's start with creating a MySQL server and a database:

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
sqlapi_source_ip=$(curl -s http://${sqlapi_ip}:8080/api/ip | jq -r .my_public_ip)
az mysql server firewall-rule create -g $rg -s $mysql_name -n public_sqlapi_aci-source --start-ip-address $sqlapi_source_ip --end-ip-address $sqlapi_source_ip
```

Now we can try to access from our previous Azure Container Instance. We will override the environment variable using the query parameters, since it was configured to point to the Azure SQL Database (and not to our Azure Database for MySQL):

```shell
# Test access to the mysql server
curl "http://${sqlapi_ip}:8080/api/mysql?SQL_SERVER_FQDN=${mysql_fqdn}"   # Not WORKING YET!!!
```

### Lab 2.2: Azure Application Gateway in front of ACI<a name="lab2.2"></a>

Could we have a reverse-proxy in front of the ACIs, to offer functionality such as SSL offload? Let's try with the Azure Application Gateway:

```shell
# variables
vnet_name=myvnet
vnet_prefix=192.168.0.0/16
subnet_appgw_name=ApplicationGateway
subnet_appgw_prefix=192.168.75.0/24
appgw_name=myappgw
appgw_sku=Standard_v2
appgw_pipname=${appgw_name}-pip
# Create vnet
az network vnet create -g $rg -n $vnet_name --address-prefix $vnet_prefix -l $location
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_appgw_name --address-prefix $subnet_appgw_prefix
# Create PIP for AppGw
az network public-ip create -g $rg -n $appgw_pipname --sku Standard -l $location
# Create App Gw
az network application-gateway create -g $rg -n $appgw_name -l $location \
        --capacity 2 --sku $appgw_sku --frontend-port 80 \
        --routing-rule-type basic --http-settings-port 80 \
        --http-settings-protocol Http --public-ip-address $appgw_pipname \
        --vnet-name $vnet_name --subnet $subnet_appgw_name \
        --servers ${web_ip} --no-wait
```

Wait until the previous command to finish, you can see the state of the Application Gateway being provisioned with:

```shell
echo "Wait until ProvisioningState is Successful"
az network application-gateway list -g $rg -o table
```

Optionally you could change the provisioned gateway to use autoscaling, this will reduce your costs changing the billing model to Capacity Units. For more information visit the [Azure Application Gateway pricing page](https://azure.microsoft.com/pricing/details/application-gateway/):

```shell
az network application-gateway update -n $appgw_name -g $rg \
    --set autoscaleConfiguration='{"minCapacity": 1, "maxCapacity": 2}' \
    --set sku='{"name": "Standard_v2","tier": "Standard_v2"}'
```

Once the application gateway has been deployed, you should be able to access its public IP address, that will be redirected to the frontend ACI. For the sake of simplicity we will use `nip.io` DNS names, that just resolve to the IP address provided in the FQDN:

```shell
appgw_pip=$(az network public-ip show -n $appgw_pipname -g $rg --query ipAddress -o tsv)
echo "You can test the application gateway deployment accessing this URL in your browser: http://${appgw_pip}.nip.io"
```

Now we can add an additional rule to the Application Gateway, to provide access to the API container over the same URL, but on a different path:

```shell
# Create new listener (so that we can used url path-based routing)
az network application-gateway http-listener create --gateway-name $appgw_name -g $rg -n containerlab --host-name "${appgw_pip}.nip.io" --frontend-ip appGatewayFrontendIP --frontend-port appGatewayFrontendPort
# Create backend pool, custom probe and backend http settings
az network application-gateway address-pool create --gateway-name $appgw_name -g $rg -n api --servers ${sqlapi_ip}
az network application-gateway probe create --gateway-name $appgw_name -g $rg -n api --path /api/healthcheck --port 8080 --protocol http --host-name-from-http-settings
az network application-gateway http-settings create --gateway-name $appgw_name -g $rg -n api --protocol http --port 8080 --probe api --host-name-from-backend-pool
# Create an URL path-based rule
az network application-gateway url-path-map create --gateway-name $appgw_name -g $rg -n MyUrlPathMap --rule-name api --paths '/api/*' --address-pool api --http-settings api
# Add new rule linking everything together (the default pool is the web farm)
az network application-gateway rule create --gateway-name $appgw_name -g $rg -n api --rule-type PathBasedRouting --http-listener containerlab --address-pool appGatewayBackendPool --http-settings appGatewayBackendHttpSettings --url-path-map MyUrlPathMap
```

Some commands to verify that everything provisioned correctly:

```shell
# Verification commands
az network application-gateway frontend-ip list --gateway-name $appgw_name -g $rg -o table
az network application-gateway frontend-port list --gateway-name $appgw_name -g $rg -o table
az network application-gateway http-listener list --gateway-name $appgw_name -g $rg -o table
az network application-gateway probe list --gateway-name $appgw_name -g $rg -o table
az network application-gateway rule list --gateway-name $appgw_name -g $rg -o table
az network application-gateway url-path-map list --gateway-name $appgw_name -g $rg
az network application-gateway address-pool list --gateway-name $appgw_name -g $rg -o table
az network application-gateway show-backend-health -n $appgw_name -g $rg
az network application-gateway http-settings list --gateway-name $appgw_name -g $rg -o table
```

At this point you can visit the web page over the Azure Application Gateway IP address and verify that the links in the `Direct access to API` section work properly.

```shell
echo "You can verify the links in the 'Direct Access to API' section of http://${appgw_pip}.nip.io"
```

## Lab 3: Azure Container Instances in a Virtual Network<a name="lab3"></a>

Note that this lab has a strong limitation: Azure Container Instances today do not query the Vnet DNS when deployed into a Vnet. Hence, in order to use private link with a vnet-injected ACI, tampering with the hosts file is going to be our only choice left. We will start creating an Azure database, as in the previous lab (or use the existing one, in which case you may proceed to the next step):

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
sql_endpoint_name=sqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $sql_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
```

We can have a look at the assigned IP address:

```shell
# Endpoint's private IP address
sql_nic_id=$(az network private-endpoint show -n $sql_endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "Private IP address for SQL server ${sql_server_name}: ${sql_endpoint_ip}"
nslookup ${sql_server_name}.privatelink.database.windows.net
```

Optionally, you could do the same with the MySQL database (note that this feature is in preview and not available in all regions):

```shell
# SQL Server private endpoint
mysql_endpoint_name=mysqlep
mysql_server_id=$(az mysql server show -n $mysql_name -g $rg -o tsv --query id)
az network private-endpoint create -n $mysql_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $mysql_server_id --group-ids mysqlServer --connection-name mySqlConnection
# Endpoint's private IP address
mysql_nic_id=$(az network private-endpoint show -n $mysql_endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
mysql_endpoint_ip=$(az network nic show --ids $mysql_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "Private IP address for MySQL server ${mysql_name}: ${mysql_endpoint_ip}"
nslookup ${mysql_name}.privatelink.database.windows.net
```

Now we can create the Azure Container Instances in the vnet subnet, pointing to the private IP address (if you want to know why we are not using the FQDN, check out the next section on private DNS). We will use the vnet and subnet IDs (and not the vnet/subnet names) to avoid ambiguity:

```shell
# Create ACI for API
vnet_id=$(az network vnet show -n $vnet_name -g $rg --query id -o tsv)
subnet_aci_id=$(az network vnet subnet show -n $subnet_aci_name --vnet-name $vnet_name -g $rg --query id -o tsv)
az container create -n api -g $rg -e "SQL_SERVER_USERNAME=$sql_username" "SQL_SERVER_PASSWORD=$sql_password" "SQL_SERVER_FQDN=${sql_server_fqdn}" --image erjosito/sqlapi:0.1 --ip-address private --ports 8080 --vnet $vnet_id --subnet $subnet_aci_id --no-wait
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
vm_pip=$(az network public-ip show  -g $rg -n $vm_pip_name --query ipAddress -o tsv)
aci_sqlapi_ip=$(az container show -n api -g $rg --query 'ipAddress.ip' -o tsv)
echo "Azure Container instance assigned IP address ${aci_sqlapi_ip}. If this is not contained in the subnet ${subnet_aci_prefix} you might want to recreate the container"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/healthcheck"
```

In the case the container was not created with the proper IP in the correct range (`192.168.1.0/24` in this lab), you can just recreate it. If it has a correct IP address, you can skip to the next step.

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
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/printenv"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/ip"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/dns?fqdn=${sql_server_fqdn}"
```

As you can see, the container's DNS server is the Vnet's DNS server, however DNS resolution is not working correctly and it is mapping the SQL Server FQDN to its public IP address, and not to the private one. Let's try to fix this deploying an Azure DNS private zone:

```shell
# Create Azure DNS private zone and records
dns_zone_name=privatelink.database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg 
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled false
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $sql_endpoint_ip
```

We can verify that the private DNS zone is working using our test VM:

```shell
# Verify DNS private zones working correctly in the VM
ssh $vm_pip "nslookup ${sql_server_fqdn}"
# Verify DNS private zones working correctly in the vnet-injected ACI: this will still resolve to the public IP
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/dns?fqdn=${sql_server_fqdn}"
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
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/dns?fqdn=${sql_server_fqdn}"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/sqlversion"
ssh $vm_pip "curl -s http://${aci_sqlapi_ip}:8080/api/sqlsrcip"
```

Now we can create a web frontend that connects to the API container. We will give it a private IP address too, otherwise it would not be able to connect to the API. In order to test the correct deployment, you could use the VM as jump host:

```shell
# Create ACI for Web frontend
az container create -n web -g $rg -e "API_URL=http://${aci_sqlapi_ip}" --image erjosito/sqlapi:0.1 --ip-address public --ports 80  --vnet $vnet_id --subnet $subnet_aci_id
aci_web_ip=$(az container show -n web -g $rg --query 'ipAddress.ip' -o tsv)
ssh $vm_pip "curl -s http://${aci_web_ip}/healthcheck"
ssh $vm_pip "curl -s http://${aci_web_ip}"
```

## Lab 4. AKS cluster in a Virtual Network<a name="lab4"></a>

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

### Lab 4.1: Install an nginx ingress controller - WORK IN PROGRESS<a name="lab4.1"></a>

In this lab we will install our ingress controller in front of our two pods. We will not use the Application Gateway Ingress Controller, since it is not fully integrated in the AKS CLI yet, but the open source nginx. You can install an installation guide for nginx with helm [here[(https://docs.nginx.com/nginx-ingress-controller/installation/installation-with-helm/)]. For example, for helm3:

```shell
helm install my-release nginx-stable/nginx-ingress
```

### Lab 4.2: protect the AKS cluster with network policies - WORK IN PROGRESS<a name="lab4.2"></a>

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

### Lab 4.3: Private cluster and private link<a name="lab4.3"></a>

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

### Lab 4.4: further exercises<a name="lab4.4"></a>

Kubernetes in general is a very rich functionality platform, and includes multiple network technologies. You can extend this lab by incorporating multiple concepts, here some examples (the list is not exhaustive by far):

* Ingress controller: configure an ingress controller to offer a common public IP address for both the web frontend and the API backend
* Pod identity and Azure Key Vault integration: inject the SQL password in the SQL API pod as a file injected from Key Vault, and not as an environment variable
* Use a service mesh to provide TLS encryption in the connectivity between containers
* Install Prometheus to measure metrics such as Requests per Second and configure alerts
* Configure an Horizontal Pod Autoscaler to auto-scale the API as more requests are sent

## Lab 5: Azure App Services for Linux<a name="lab5"></a>

For this lab we will use Azure Application Services for Linux. Let us create a resource group and a SQL Server. Regarding the location of the web app, eastus and westus2 are two good candidates, since it is where the preview for private link for webapps is running (see [here](https://docs.microsoft.com/azure/private-link/create-private-endpoint-webapp-portal)):

```shell
# Resource group
rg=containerlab
location=eastus
az group create -n $rg -l $location
# Azure SQL
sql_server_name=myserver$RANDOM
sql_db_name=mydb
sql_username=azure
sql_password=Microsoft123!
az sql server create -n $sql_server_name -g $rg -l $location --admin-user $sql_username --admin-password $sql_password
az sql db create -n $sql_db_name -s $sql_server_name -g $rg -e Basic -c 5 --no-wait
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
# Note: it might take some seconds/minutes for the web app to come up and answer successfully the following command
curl "http://${app_url_api}/api/healthcheck"
```

As with previous labs, we need to add the outbound public IP of the Web App to the firewall rules of the SQL Server, and verify that SQL access is working properly:

```shell
# SQL Server firewall rules
sqlapi_webapp_source_ip=$(curl -s http://${app_url_api}/api/ip | jq -r .my_public_ip)
az sql server firewall-rule create -g $rg -s $sql_server_name -n webapp-sqlapi-source --start-ip-address $sqlapi_webapp_source_ip --end-ip-address $sqlapi_webapp_source_ip
az sql server firewall-rule list -g $rg -s $sql_server_name -o table
curl -s "http://${app_url_api}/api/sqlversion"
```

Now we can deploy a second app in our service plan with the web frontend component:

```shell
# Create Web App for web frontend
az webapp create -n $app_name_web -g $rg -p $svcplan_name --deployment-container-image-name erjosito/whoami:0.1
az webapp config appsettings set -n $app_name_web -g $rg --settings "API_URL=http://${app_url_api}"
az webapp restart -n $app_name_web -g $rg
app_url_web=$(az webapp show -n $app_name_web -g $rg --query defaultHostName -o tsv)
echo "You can point your browser to http://${app_url_web} to verify the front end"
```

### Lab 5.1. Azure App Services with Vnet integration and private link<a name="lab51"></a>

This lab is built on top of the previous one, you will need to have deployed the Web App and the SQL server before proceeding here (see the instructions in the previous section). Once you do that, we can integrate the Web App and the SQL Server in the Vnet. Let's start by creating the vnet with two subnets:

```shell
# Create Virtual Network and subnets
vnet_name=myvnet
vnet_prefix=192.168.0.0/16
subnet_webapp_be_name=webapp-be
subnet_webapp_be_prefix=192.168.5.0/24
subnet_sql_name=sql
subnet_sql_prefix=192.168.2.0/24
az network vnet create -n $vnet_name -g $rg --address-prefix $vnet_prefix
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_webapp_be_name --address-prefix $subnet_webapp_be_prefix
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_sql_name --address-prefix $subnet_sql_prefix
```

We can start with the private endpoint for the SQL database, since we have already seen in previous labs how to do that:

```shell
# SQL private endpoint
sql_endpoint_name=sqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $sql_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-id sqlServer --connection-name sqlConnection
sql_nic_id=$(az network private-endpoint show -n $sql_endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $sql_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
```

Before configuring private link for the web app, let's make a note on the egress public IP that the Web App is using to reach out to the Internet:

```shell
old_webapp_source_ip=$(curl -s http://${app_url_api}/api/ip | jq -r .my_public_ip)
echo "Before vnet integration, the egress IP address for the web app is ${old_webapp_source_ip}"
```

Now we can integrate the Web App with the vnet, and verify that the web app has a new outbound public IP:

```shell
# Vnet integration
az webapp vnet-integration add -n $app_name_api -g $rg --vnet $vnet_name --subnet $subnet_webapp_be_name
az webapp vnet-integration list -n $app_name_api -g $rg -o table
new_webapp_source_ip=$(curl -s http://${app_url_api}/api/ip | jq -r .my_public_ip)
echo "After vnet integration, the egress IP address for the web app is ${new_webapp_source_ip} (the old one was ${old_webapp_source_ip})"
```

Let us verify DNS resolution for the SQL server's FQDN:

```shell
curl -s "http://${app_url_api}/api/dns?fqdn=${sql_server_fqdn}"
```

If it is not working, it means that the web app cannot leverage Azure's native DNS. A workaround is configuring a test VM that will act as DNS forwarder:

We can integrate the frontend of the webapp in our vnet as well, so that it is accessible only from within the vnet or from on-premises. In order to test this, we will need a VM inside the virtual network:

```shell
# Create VM for testing purposes
subnet_vm_name=vm
subnet_vm_prefix=192.168.10.0/24
vm_name=testvm
aks_node_size=Standard_B2ms
vm_size=Standard_B2ms
vm_pip_name=${vm_name}-pip
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_vm_name --address-prefix $subnet_vm_prefix
az vm create -n $vm_name -g $rg --vnet-name $vnet_name --subnet $subnet_vm_name --public-ip-address $vm_pip_name --generate-ssh-keys --image ubuntuLTS --size $vm_size
vm_pip=$(az network public-ip show  -g $rg -n $vm_pip_name --query ipAddress -o tsv)
```

```shell 
# Install a DNS server and apache on the test VM
dnsserver_ip=$(az network public-ip show  -g $rg -n $vm_pip_name --query ipAddress -o tsv)
dnsserver_nic_id=$(az vm show -n $vm_name -g $rg --query 'networkProfile.networkInterfaces[0].id' -o tsv)
dnsserver_privateip=$(az network nic show --ids $dnsserver_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "DNS server deployed to $dnsserver_privateip, $dnsserver_ip"
echo "Verifying name resolution for ${sql_server_fqdn}:"
ssh-keyscan -H $dnsserver_ip >> ~/.ssh/known_hosts
ssh $dnsserver_ip "nslookup ${sql_server_fqdn}"
echo "IP configuration of the VM:"
ssh $dnsserver_ip "ip a"
echo "Installing DNS:"
ssh $dnsserver_ip "sudo apt update && sudo apt -y install apache2 dnsmasq"
```

Next step if configuring Azure DNS to resolve the privatelink zone to the internal IP address:

```shell
# Create Azure DNS private zone and records: database.windows.net
dns_zone_name=privatelink.database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg 
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled false
# Create record (private dns zone integration not working in the CLI)
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $sql_endpoint_ip
# Verification: list recordsets in the zone
az network private-dns record-set list -z $dns_zone_name -g $rg -o table
az network private-dns record-set a show -n $sql_server_name -z $dns_zone_name -g $rg --query aRecords -o table
```

And we need to configure our app to use the DNS server we just installed:

```shell
# Configure custom DNS server for webapp
az webapp config appsettings set -n $app_name_api -g $rg --settings "WEBSITE_DNS_SERVER=${dnsserver_privateip}"
az webapp restart -n $app_name_api -g $rg
```

We can test now the resolution of the SQL Server FQDN, and access to the database over the internal IP address:

```shell
# Verify DNS resolution and SQL access
curl -s "http://${app_url_api}/api/dns?fqdn=${sql_server_fqdn}"
curl -s "http://${app_url_api}/api/sqlversion"
curl -s "http://${app_url_api}/api/sqlsrcip"
```

### Lab 5.2. Azure App Services with Vnet integration and private link: frontend<a name="lab52"></a>

Now we can create a private endpoint for our web app, see [here](https://docs.microsoft.com/azure/private-link/create-private-endpoint-webapp-portal) for more information on private link for Web Apps:

```shell
# Webapp private endpoint
subnet_webapp_fe_name=webapp-fe
subnet_webapp_fe_prefix=192.168.6.0/24
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_webapp_fe_name --address-prefix $subnet_webapp_fe_prefix
webapp_endpoint_name=mywebep
svcplan_id=$(az appservice plan show -n $svcplan_name -g $rg -o tsv --query id)
webapp_id=$(az webapp show -n $app_name_api -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_webapp_fe_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
# Private link endpoinst only work for premium SKU
az appservice plan update -n $svcplan_name -g $rg --sku P1V2
group_id=sites
# az network private-link-resource list -n $app_name_api -g $rg --type Microsoft.Web -o table  # DOES NOT WORK
az network private-endpoint create -n $webapp_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_webapp_fe_name --private-connection-resource-id $webapp_id --group-id $group_id --connection-name webappConnection
webapp_nic_id=$(az network private-endpoint show -n $webapp_endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
webapp_endpoint_ip=$(az network nic show --ids $webapp_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
```

From our Virtual Machine we should now be able to reach the Web App on its private IP:

```shell
# Reach the web app's private IP
ssh $vm_pip "curl -s http://${webapp_endpoint_ip}:8080/api/healthcheck"
```

Next we can configure vnet integration for the web frontend app in the subnet `$subnet_webapp_be_name`:

```shell
# Configure vnet integration for web frontend
az webapp vnet-integration add -n $app_name_web -g $rg --vnet $vnet_name --subnet $subnet_webapp_be_name
az webapp vnet-integration list -n $app_name_web -g $rg -o table
```

And lastly, we can modify the environment variable for the web frontend to reach to the API over its new private IP

```shell
# Modify environment variable in web frontend, so that it connects to the API over the private IP
az webapp config appsettings set -n $app_name_web -g $rg --settings "API_URL=http://${webapp_endpoint_ip}"
az webapp restart -n $app_name_web -g $rg
echo "You can point your browser to http://${app_url_web} to verify the front end"
```

### Lab 5.3. Azure Key Vault, Azure Application Gateway and certificates - WORK IN PROGRESS<a name="lab53"></a>

Feel free to jump to the next lab [Lab 6: Azure Windows Web App](#lab6)

An Azure Application Gateway with WAF in front of an Azure Web App is an effective way of increasing overall security for your web applicaiton. The Azure Application Gateway will require a digital certificate that can be imported from the Azure Key Vault.

```shell
# Create key vault and import certificate
# The cert must be P12 and not PEM to be correctly imported from the webapp
keyvault_name=akv$RANDOM
cert_name=mycert
cert_file_name=mycert.pfx  # cert with private key
cert_file_password=yoursupersecretpassword # Password with which you exported the certificate
az keyvault create -n $keyvault_name -g $rg -l $location
az keyvault certificate import -n $cert_name --vault-name $keyvault_name -f $cert_file_name --password $cert_file_password
```

```shell
# Configure logging for key vault
storage_account_name=storage$RANDOM
az storage account create -n $storage_account_name -g $rg --sku Standard_LRS
storage_account_id=$(az storage account show -n $storage_account_name -g $rg --query id -o tsv)
storage_account_key=$(az storage account keys list -n $storage_account_name -g $rg --query '[0].value' -o tsv)
keyvault_id=$(az keyvault show -n $keyvault_name -g $rg --query id -o tsv)
az monitor diagnostic-settings create --resource $keyvault_id -n akvdiagnostics --storage-account $storage_account_name --logs '[
        {
          "category": "AuditEvent",
          "enabled": true,
          "retentionPolicy": {
            "enabled": false,
            "days": 0
          }
        }
      ]'
container='insights-logs-auditevent'
log_filename=/tmp/akv_audit.log
# Create a dummy secret to test the logs
az keyvault secret set --vault-name $keyvault_name -n dummysecret --value dummyvalue
# It might take some seconds to generate the log blob
az storage blob list --account-name $storage_account_name --account-key $storage_account_key -c $container --query '[].name' -o tsv
```

```shell
# Take the name of the last blob and print it jq-filtered
blob_name=$(az storage blob list --account-name $storage_account_name --account-key $storage_account_key -c $container --query '[-1].name' -o tsv)
az storage blob download --account-name $storage_account_name --account-key $storage_account_key -c $container -n $blob_name -f $log_filename >/dev/null
jq -r '[.time, .identity.claim.appid, .operationName, .resultSignature, .callerIpAddress] | @tsv' $log_filename
```

```shell
# Modify default access action to Deny and add our own IP address
az keyvault update -n $keyvault_name -g $rg --default-action Deny
my_pip=$(curl -s4 ifconfig.co)
az keyvault network-rule add -n $keyvault_name -g $rg --ip-address $my_pip
```

```shell
# Optionally, add the last unauthorized IP to the list of allowed addresses
last_pip=$(jq -r 'select(.resultSignature == "Unauthorized") | .callerIpAddress' $log_filename | tail -1)
last_pip_org=$(curl -s "https://ipapi.co/${last_pip}/json/" | jq -r '.org')
if [[ $last_pip_org == "MICROSOFT-CORP-MSN-AS-BLOCK" ]]
then
  echo "IP address ${last_pip} belongs to ${last_pip_org}, adding to the list of allowed IP addresses"
  az keyvault network-rule add -n $keyvault_name -g $rg --ip-address $last_pip
else
  echo "IP address ${last_pip} does not belong to Microsoft, but to $last_pip_org"
fi
```

```shell
# Import SSL cert to web app
websites_objectid=f8daea97-62e7-4026-becf-13c2ea98e8b4 # Microsoft.Azure.WebSites SP
az keyvault set-policy -n $keyvault_name -g $rg --object-id $websites_objectid \
    --certificate-permissions get getissuers list listissuers \
    --secret-permissions get list
#keyvault_id=$(az keyvault show -n $keyvault_name -g $rg --query id -o tsv)
#az role assignment create --assignee-object-id $websites_objectid --scope $keyvault_id --role Reader # this shouldnt be required
cert_id=$(az keyvault certificate show --vault-name $keyvault_name -n $cert_name --query id -o tsv)
az webapp config ssl import -n $app_name_api -g $rg --key-vault $keyvault_name --key-vault-certificate-name $cert_name
# Custom hostname
webapp_custom_hostname=sqlapi-webapp
webapp_custom_domain=contoso.com
webapp_custom_fqdn=${webapp_custom_hostname}.${webapp_custom_domain}
# Update DNS (assuming a DNS zone for the domain exists in the current subscription)
zone_name=$(az network dns zone list -o tsv --query "[?name=='${webapp_custom_domain}'].name")
if [[ "$zone_name" == "$webapp_custom_domain" ]]
then
     zone_rg=$(az network dns zone list -o tsv --query "[?name=='${webapp_custom_domain}'].resourceGroup")
     echo "Azure DNS zone ${webapp_custom_domain} found in resource group ${zone_rg}, using Azure DNS for accessing the app"
     az network dns record-set cname set-record -z ${webapp_custom_domain} -n ${webapp_custom_hostname} -g $zone_rg -c ${app_url_api}
     az webapp config hostname add --webapp-name $app_name_api -g $rg --hostname $webapp_custom_fqdn
     echo "Point your browser to https://${webapp_custom_fqdn}"
else
     echo "Azure DNS zone ${webapp_custom_domain} not found in subscription, you might want to use the domain nip.io for this web app"
fi
# Bind certificate to custom domain
cert_thumbprint=$(az keyvault certificate show --vault-name $keyvault_name -n $cert_name --query x509ThumbprintHex -o tsv)
az webapp config ssl bind -n $app_name_api -g $rg --certificate-thumbprint $cert_thumbprint --ssl-type sni
echo "Point your browser to https://${webapp_custom_fqdn}/api/healthcheck"
```

```shell
# Create vnet and App Gw
vnet_name=myvnet
vnet_prefix=192.168.0.0/16
az network vnet create -g $rg -n $vnet_name --address-prefix $vnet_prefix -l $location
subnet_appgw_name=ApplicationGateway
subnet_appgw_prefix=192.168.75.0/24
appgw_name=myappgw
appgw_sku=Standard_v2
appgw_pipname=${appgw_name}-pip
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_appgw_name --address-prefix $subnet_appgw_prefix
az network public-ip create -g $rg -n $appgw_pipname --sku Standard -l $location
az network application-gateway create -g $rg -n $appgw_name -l $location \
        --capacity 2 --sku $appgw_sku --frontend-port 80 \
        --routing-rule-type basic --http-settings-port 80 \
        --http-settings-protocol Http --public-ip-address $appgw_pipname \
        --vnet-name $vnet_name --subnet $subnet_appgw_name \
        --servers dummy.com --no-wait
appgw_pip=$(az network public-ip show -n $appgw_pipname -g $rg --query ipAddress -o tsv)
```

```shell
# Create service endpoint for the app gw to access the keyvault privately
az keyvault network-rule list -n $keyvault_name -g $rg -o table
subnet_appgw_id=$(az network vnet subnet show --vnet-name $vnet_name -n $subnet_appgw_name -g $rg --query id -o tsv)
az network vnet subnet update -n $subnet_appgw_name --vnet-name $vnet_name -g $rg --service-endpoints Microsoft.KeyVault
az keyvault network-rule add -n $keyvault_name -g $rg --subnet $subnet_appgw_id
```

```shell
# Allow GatewayManager IP address in the AKV ***NOT WORKING***
# GatewayManager prefixes not in the JSON file for ip ranges nor in the command az network list-service-tags (GatewayManager is a non-regional svc tag)
url1=https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519
url2=$(curl -Lfs "${url1}" | grep -Eoi '<a [^>]+>' | grep -Eo 'href="[^\"]+"' | grep "download.microsoft.com/download/" | grep -m 1 -Eo '(http|https)://[^"]+')
prefixes=$(curl -s $url2 | jq -c '.values[] | select(.name | contains ("GatewayManager")) | .properties.addressPrefixes')
prefixes2=$(echo $prefixes | tr -d "[]," | tr -s '"' ' ')
i=0
for prefix in $prefixes2; do i=$((i+1)); az keyvault network-rule add -n $keyvault_name -g $rg --ip-address $prefix; done
```

```shell
# Import cert from keyvault into app gateway
appgw_identity_name=appgw
az identity create -n $appgw_identity_name -g $rg
appgw_identity_id=$(az identity show -g $rg -n $appgw_identity_name --query id -o tsv)
appgw_identity_principalid=$(az identity show -g $rg -n $appgw_identity_name --query principalId -o tsv)
appgw_identity_objectid=$(az ad sp show --id $appgw_identity_principalid --query objectId -o tsv)
az network application-gateway identity assign -g $rg --gateway-name $appgw_name --identity $appgw_identity_id
az keyvault set-policy -n $keyvault_name -g $rg --object-id $appgw_identity_objectid --certificate-permissions get getissuers list listissuers --secret-permissions get list
az keyvault update -n $keyvault_name -g $rg --enable-soft-delete
cert_id=$(az keyvault certificate show --vault-name $keyvault_name -n $cert_name --query id -o tsv)
#cert_id="https://${keyvault_name}.vault.azure.net/certificates/${cert_name}"
az network application-gateway ssl-cert create --gateway-name $appgw_name -g $rg -n $cert_name --key-vault-secret-id $cert_id  # NOT WORKING!!!!
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
app_file_url=https://raw.githubusercontent.com/jelledruyts/InspectorGadget/master/Page/default.aspx
app_file_name=test.aspx
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
sql_endpoint_name=sqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $sql_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-ids sqlServer --connection-name sqlConnection
# Get private endpoint ip
nsql_ic_id=$(az network private-endpoint show -n $sql_endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "Private IP address for SQL server ${sql_server_name}: ${sql_endpoint_ip}"
```

We can use Azure DNS private zones to provide DNS resolution for our web app, and create an A record that maps the SQL server FQDN to the private IP address:

```shell
# Create Azure DNS private zone and records: database.windows.net
dns_zone_name=privatelink.database.windows.net
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
ssh $dnsserver_ip "sudo apt -y update"
ssh $dnsserver_ip "sudo apt -y install apache2 dnsmasq"
```

You could decide to use the previous test VM for DNS as well, in which case you can set the variables like this:

```shell
dnsserver_ip=$(az network public-ip show  -g $rg -n $vm_pip_name --query ipAddress -o tsv)
dnsserver_nic_id=$(az vm show -n $vm_name -g $rg --query 'networkProfile.networkInterfaces[0].id' -o tsv)
dnsserver_privateip=$(az network nic show --ids $dnsserver_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "DNS server deployed to $dnsserver_privateip, $dnsserver_ip"
echo "IP configuration of the VM:"
ssh $dnsserver_ip "ip a"
ssh $dnsserver_ip "sudo apt -y install apache2 dnsmasq-base"
```

There are two options to force the web app to use the DNS server. The first one is configuring our DNS server as the default for the whole vnet. Bouncing the vnet integration (deleting and recreating) might be required so that the web app takes the changes:

```shell
# Configure web app for DNS - Option 1:
# DNS server as server for the vnet (required only if not setting the app setting)
az network vnet update -n $vnet_name -g $rg --dns-servers $dnsserver_privateip
# Bounce the vnet integration to take the new DNS config
az webapp vnet-integration remove -n $app_name_api -g $rg
az webapp vnet-integration add -n $app_name_api -g $rg --vnet $vnet_name --subnet $subnet_webapp_be_name
```

The second option consists in instructing the web app to use the DNS server in the VM that we just deployed. The benefit of this option is that other VMs in the vnet will not be affected.

```shell
# Configure web app for DNS - Option 2:
# Change web app DNS settings (https://www.azuretechguy.com/how-to-change-the-dns-server-in-azure-app-service)
az webapp config appsettings set -n $app_name_api -g $rg --settings "WEBSITE_DNS_SERVER=${dnsserver_privateip}"
az webapp restart -n $app_name_api -g $rg
```

Now you can send the SQL uery over the app to `SELECT CONNECTIONPROPERTY('client_net_address')`, it should be using the private IP address

## Lab 7. Azure Virtual Machines and private link:<a name="lab7"></a>

We can run a similar lab based on Azure Virtual Machines. First we well deploy some basic infrastructure, if you are starting from scratch:

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
subnet_vm_name=vm
subnet_vm_prefix=192.168.13.0/24
az network vnet create -g $rg -n $vnet_name --address-prefix $vnet_prefix -l $location
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_sql_name --address-prefix $subnet_sql_prefix
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_vm_name --address-prefix $subnet_vm_prefix
```

We will now create an Azure VM based on Ubuntu 18.04, and install the API code with a Custom Script Extension:

```shell
vm_name=apivm
vm_nsg_name=${vm_name}-nsg
vm_pip_name=${vm_name}-pip
vm_disk_name=${vm_name}-disk0
vm_sku=Standard_B2ms
publisher=Canonical
offer=UbuntuServer
sku=18.04-LTS
image_urn=$(az vm image list -p $publisher -f $offer -s $sku -l $location --query '[0].urn' -o tsv)
# Deploy VM
az vm create -n $vm_name -g $rg -l $location --image $image_urn --size $vm_sku --generate-ssh-keys \
  --os-disk-name $vm_disk_name --os-disk-size-gb 32 \
  --vnet-name $vnet_name --subnet $subnet_vm_name \
  --nsg $vm_nsg_name --nsg-rule SSH --public-ip-address $vm_pip_name
# Add rule to NSG on port 8080
az network nsg rule create -n TCP8080 --nsg-name $vm_nsg_name -g $rg \
  --protocol Tcp --access Allow --priority 105 --direction Inbound \
  --destination-port-ranges 8080
# Install app, this will take a while (a bunch of apt updates, installs, etc).
# You might have to Ctrl-C this, it hangs when executing the app (for some reason i am not able to run it as a background task)
script_url=https://raw.githubusercontent.com/erjosito/whoami/master/api-vm/cse.sh
script_command='./cse.sh'
az vm extension set -n customScript --vm-name $vm_name -g $rg --publisher Microsoft.Azure.Extensions \
  --protected-settings "{\"fileUris\": [\"${script_url}\"],\"commandToExecute\": \"${script_command}\"}"
# Set environment variables
# command="export SQL_SERVER_USERNAME=${sql_username} && export SQL_SERVER_PASSWORD=${sql_password}"
# az vm run-command invoke -n $vm_name -g $rg --command-id RunShellScript --scripts "${command}"
# az vm run-command invoke -n $vm_name -g $rg --command-id RunShellScript --scripts 'export SQL_SERVER_USERNAME=$1 && export SQL_SERVER_PASSWORD=$2' \
#    --parameters $sql_username $sql_password
# Get public IP
vm_pip_ip=$(az network public-ip show -n $vm_pip_name -g $rg --query ipAddress -o tsv)
echo "You can SSH to $vm_pip_ip"
# Send a probe to the app
curl -s ${vm_pip_ip}:8080/api/healthcheck
```

You can explore the different endpoints of the API:

```shell
curl -s ${vm_pip_ip}:8080/api/ip
curl -s ${vm_pip_ip}:8080/api/printenv
```

We can now create a private link endpoint for our SQL database:

```shell
# Create private link endpoint
sql_endpoint_name=sqlep
sql_server_id=$(az sql server show -n $sql_server_name -g $rg -o tsv --query id)
az network vnet subnet update -n $subnet_sql_name -g $rg --vnet-name $vnet_name --disable-private-endpoint-network-policies true
az network private-endpoint create -n $sql_endpoint_name -g $rg --vnet-name $vnet_name --subnet $subnet_sql_name --private-connection-resource-id $sql_server_id --group-id sqlServer --connection-name sqlConnection
sql_nic_id=$(az network private-endpoint show -n $sql_endpoint_name -g $rg --query 'networkInterfaces[0].id' -o tsv)
sql_endpoint_ip=$(az network nic show --ids $sql_nic_id --query 'ipConfigurations[0].privateIpAddress' -o tsv)
echo "Private IP address for SQL server ${sql_server_name}: ${sql_endpoint_ip}"
nslookup ${sql_server_fqdn}
nslookup ${sql_server_name}.privatelink.database.windows.net
```

And the private DNS zone to our vnet with the privatelink record, so that the VM resolves the SQL Server's FQDN to the private IP:

```shell
# Create private DNS
dns_zone_name=privatelink.database.windows.net
az network private-dns zone create -n $dns_zone_name -g $rg
az network private-dns link vnet create -g $rg -z $dns_zone_name -n myDnsLink --virtual-network $vnet_name --registration-enabled false
az network private-dns record-set a create -n $sql_server_name -z $dns_zone_name -g $rg
az network private-dns record-set a add-record --record-set-name $sql_server_name -z $dns_zone_name -g $rg -a $sql_endpoint_ip
```

We can use the DNS endpoint of our VM to verify dns resolution:

```shell
# DNS resolution verification
curl -s "http://${vm_pip_ip}:8080/api/dns?fqdn=${sql_server_fqdn}"
```

And we can try to get reach the SQL Server over its private IP address:

```shell
# Test SQL query
curl "http://${vm_pip_ip}:8080/api/sqlsrcip?SQL_SERVER_FQDN=${sql_server_fqdn}&SQL_SERVER_USERNAME=${sql_username}&SQL_SERVER_PASSWORD=${sql_password}"
```

We can see an interesting fact regarding private link endpoints: /32 routes are created. We can inspect the effective route table to verify that:

```shell
# Check effective routes generated by private link
vm_nic_name=${vm_name}VMNic
az network nic show-effective-route-table -n $vm_nic_name -g $rg -o table
```

### Azure Firewall between VM and private link endpoint

To Do

```shell
# Create Azure Firewall
azfw_name=myazfw
azfw_pip_name=myazfw-pip
subnet_azfw_name=AzureFirewallSubnet
subnet_azfw_prefix=192.168.15.0/24
logws_name=log$RANDOM
az network vnet subnet create -g $rg --vnet-name $vnet_name -n $subnet_azfw_name --address-prefix $subnet_azfw_prefix
az network public-ip create -g $rg -n $azfw_pip_name --sku standard --allocation-method static -l $location
azfw_ip=$(az network public-ip show -g $rg -n $azfw_pip_name --query ipAddress -o tsv)
az network firewall create -n $azfw_name -g $rg -l $location
azfw_id=$(az network firewall show -n $azfw_name -g $rg -o tsv --query id)
az monitor log-analytics workspace create -n $logws_name -g $rg
logws_id=$(az monitor log-analytics workspace show -n $logws_name -g $rg --query id -o tsv)
logws_customerid=$(az monitor log-analytics workspace show -n $logws_name -g $rg --query customerId -o tsv)
az monitor diagnostic-settings create -n mydiag --resource $azfw_id --workspace $logws_id \
    --metrics '[{"category": "AllMetrics", "enabled": true, "retentionPolicy": {"days": 0, "enabled": false }, "timeGrain": null}]' \
    --logs '[{"category": "AzureFirewallApplicationRule", "enabled": true, "retentionPolicy": {"days": 0, "enabled": false}}, 
            {"category": "AzureFirewallNetworkRule", "enabled": true, "retentionPolicy": {"days": 0, "enabled": false}}]'
az network firewall ip-config create -f $azfw_name -n azfw-ipconfig -g $rg --public-ip-address $azfw_pip_name --vnet-name $vnet_name
az network firewall update -n $azfw_name -g $rg
azfw_private_ip=$(az network firewall show -n $azfw_name -g $rg -o tsv --query 'ipConfigurations[0].privateIpAddress')
# az network firewall application-rule create -f $azfw_name -g $rg -c AllowAll --protocols Http=8080 Https=443 --target-fqdns "*" --source-addresses $vnet_prefix -n Allow-all --priority 200 --action Allow
az network firewall network-rule create -f $azfw_name -g $rg -c VnetTraffic --protocols Any --destination-addresses $vnet_prefix --destination-ports '*' --source-addresses $vnet_prefix \
  -n Allow-Vnet-Traffic --priority 210 --action Allow
```

Now we can create a route-table in the VM's subnet to send traffic to the SQL endpoint to the firewall:

```shell
rt_name=vmrt
az network route-table create -n $rt_name -g $rg -l $location
rt_id=$(az network route-table show -n $rt_name -g $rg --query id -o tsv)
az network route-table route create -n sqlendpoint --route-table-name $rt_name -g $rg --next-hop-type VirtualAppliance --address-prefix "${sql_endpoint_ip}/32" --next-hop-ip-address $azfw_private_ip
az network vnet subnet update -g $rg --vnet-name $vnet_name -n $subnet_vm_name --route-table $rt_id
```

The effective routes should look different now, and the SQL server private endpoint should be now reachable through the Azure Firewall:

```shell
# Check effective routes generated by private link
vm_nic_name=${vm_name}VMNic
az network nic show-effective-route-table -n $vm_nic_name -g $rg -o table
```

And consequently, we should put the corresponding route-table in the private link subnet. Note that this is not going to work, as documented [here](https://docs.microsoft.com/azure/private-link/private-endpoint-overview#limitations):

```shell
rt_name=plinkrt
az network route-table create -n $rt_name -g $rg -l $location
rt_id=$(az network route-table show -n $rt_name -g $rg --query id -o tsv)
az network route-table route create -n vmsubnet --route-table-name $rt_name -g $rg --next-hop-type VirtualAppliance --address-prefix "${subnet_vm_prefix}" --next-hop-ip-address $azfw_private_ip
az network vnet subnet update -g $rg --vnet-name $vnet_name -n $subnet_sql_name --route-table $rt_id
```

Let us generate some traffic. Note that the firewall should drop the traffic, since there is asymmetric routing at this point:

```shell
# Test SQL query
curl "http://${vm_pip_ip}:8080/api/sqlsrcip?SQL_SERVER_FQDN=${sql_server_fqdn}&SQL_SERVER_USERNAME=${sql_username}&SQL_SERVER_PASSWORD=${sql_password}"
```

We can have a look at the firewall logs with this query to verify that the traffic was indeed going through the Azure Firewall and was dropped:

```shell
# Show Azure Firewall logs
query_nw_rule='AzureDiagnostics
| where Category == "AzureFirewallNetworkRule"
| parse msg_s with Protocol " request from " SourceIP ":" SourcePortInt:int " to " TargetIP ":" TargetPortInt:int *
| parse msg_s with * ". Action: " Action1a
| parse msg_s with * " was " Action1b " to " NatDestination
| parse msg_s with Protocol2 " request from " SourceIP2 " to " TargetIP2 ". Action: " Action2
| extend SourcePort = tostring(SourcePortInt),TargetPort = tostring(TargetPortInt)
| extend Action = case(Action1a == "", case(Action1b == "",Action2,Action1b), Action1a),Protocol = case(Protocol == "", Protocol2, Protocol),SourceIP = case(SourceIP == "", SourceIP2, SourceIP),TargetIP = case(TargetIP == "", TargetIP2, TargetIP),SourcePort = case(SourcePort == "", "N/A", SourcePort),TargetPort = case(TargetPort == "", "N/A", TargetPort),NatDestination = case(NatDestination == "", "N/A", NatDestination)
| project TimeGenerated, msg_s, Protocol, SourceIP,SourcePort,TargetIP,TargetPort,Action, NatDestination'
# This might take a while to work
az monitor log-analytics query -w $logws_customerid --analytics-query $query_nw_rule -o tsv
```

As workaround, we could tune our AzFW to always do SNAT:

```shell
# Customized SNAT behavior of AzFW
az network firewall update -n $azfw_name -g $rg --private-ranges $subnet_vm_prefix
```

We can test again access to the database. Note that the firewall will now SNAT the traffic, and hence the SQL server will see as source an IP address in the Azure Firewall's subnet:

```shell
# Test SQL query
curl "http://${vm_pip_ip}:8080/api/sqlsrcip?SQL_SERVER_FQDN=${sql_server_fqdn}&SQL_SERVER_USERNAME=${sql_username}&SQL_SERVER_PASSWORD=${sql_password}"
```

If you want to reverse the Azure Firewall SNAT behavior to its default:

```shell
# Customized SNAT behavior of AzFW
az network firewall update -n $azfw_name -g $rg --private-ranges IANAPrivateRanges
```


## Cleanup

Do not forget to `az group delete -n $rg -y --no-wait`!
