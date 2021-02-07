###############################################
# Azure Container Instances with Azure CLI
#
# Tested with zsh (if run with bash there are probably A LOT of missing "")
#
# Jose Moreno, January 2021
###############################################

# Variables
location=westeurope
aci_name_prefix=sqlapi
vnet_name=acivnet
vnet_prefix=192.168.0.0/16
appgw_subnet_name=appgw
appgw_subnet_prefix=192.168.1.0/24
aci_subnet_name=aci
aci_subnet_prefix=192.168.2.0/24
sql_subnet_name=sql
sql_subnet_prefix=192.168.3.0/24

# Argument parsing (can overwrite the previously initialized variables)
for i in "$@"
do
     case $i in
          -g=*|--resource-group=*)
               rg="${i#*=}"
               shift # past argument=value
               ;;
          -l=*|--location=*)
               location="${i#*=}"
               shift # past argument=value
               ;;
     esac
done
set -- "${POSITIONAL[@]}" # restore positional parameters

# Function to generate random string
function random_string () {
    if [[ -n "$1" ]]
    then
      length=$1
    else
      length=6
    fi
    echo $(tr -dc a-z </dev/urandom | head -c $length ; echo '')
}

# Generate a 6-character, lower-case alphabetic, random string
unique_id=$(random_string 6)

# Create test RG, ACR, AKV and Vnet
az group create -n "$rg" -l "$location"
acr_name="acilab${unique_id}"
az acr create -n "$acr_name" -g "$rg" --sku Premium
az network vnet create -n "$vnet_name" -g "$rg" --address-prefix "$vnet_prefix"
az network vnet subnet create --vnet-name "$vnet_name" -g "$rg" -n "$appgw_subnet_name" --address-prefix "$appgw_subnet_prefix"
az network vnet subnet create --vnet-name "$vnet_name" -g "$rg" -n "$aci_subnet_name" --address-prefix "$aci_subnet_prefix"
az network vnet subnet create --vnet-name "$vnet_name" -g "$rg" -n "$sql_subnet_name" --address-prefix "$sql_subnet_prefix"
akv_name="acilab${unique_id}"
az keyvault create -n "$akv_name" -g "$rg" -l "$location"
sp_appid=$(az account show --query user.name -o tsv)
sp_oid=$(az ad sp show --id "$sp_appid" --query objectId -o tsv)
az keyvault set-policy -n "$akv_name" --object-id "$sp_oid" \
        --secret-permissions get list set \
        --certificate-permissions create import list setissuers update \
        --key-permissions create get import sign verify 