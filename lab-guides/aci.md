# Azure Container Instances

In these lab guides you will go through setting up Azure Container Instances with some advanced Azure networking features such as private link or the Azure App Gateway. This guide contains the following labs:

* [Lab 1: Azure Container Instances with public IP addresses](#lab1)
  * [Lab 1.1: MySQL](#lab1.1)
  * [Lab 1.2: App Gateway](#lab1.2)
* [Lab 3: Azure Container Instances with private IP addresses](#lab2)

## Lab 1: Azure Container Instances (public IP addresses)<a name="lab1"></a>

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

### Lab 1.1: Azure Container Instances with Azure MySQL<a name="lab1.1"></a>

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

### Lab 1.2: Azure Application Gateway in front of ACI<a name="lab1.2"></a>

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

## Lab 2: Azure Container Instances in a Virtual Network<a name="lab2"></a>

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
