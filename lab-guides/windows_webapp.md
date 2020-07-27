# Windows Web Apps

In these lab guides you will go through setting up Azure Windows App Services with some advanced Azure networking features such as private link or the Azure App Gateway. This guide contains the following labs:

* [Lab 1: Create Web App and Azure SQL private link](#lab1)

## Lab 1. Azure Windows Web App Services with Vnet integration and private link:<a name="lab1"></a>

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
