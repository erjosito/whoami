# Azure Linux Web Apps

In these lab guides you will go through setting up Azure Linux App Services with some advanced Azure networking features such as private link or the Azure App Gateway. This guide contains the following labs:

* [Prerequisite: Create Linux Web App](#lab5)
* [Lab 1: Azure Linux Web Application with Vnet integration](#lab51)
* [Lab 2: Azure Linux Web App with private link for frontend (NOT AVAILABLE YET)](#lab52)

## Prerequisite: create Azure App Services for Linux<a name="create"></a>

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

### Lab 1. Azure App Services with Vnet integration and private link<a name="lab51"></a>

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

### Lab 2. Azure App Services with Vnet integration and private link: frontend<a name="lab52"></a>

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
