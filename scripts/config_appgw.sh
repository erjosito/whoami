###############################################
# Azure Container Instances with Azure CLI
#
# Tested with zsh (if run with bash there are probably A LOT of missing "")
#
# Jose Moreno, January 2021
###############################################

# Argument parsing (can overwrite the previously initialized variables)
for i in "$@"
do
     case $i in
          -g=*|--resource-group=*)
               rg="${i#*=}"
               shift # past argument=value
               ;;
          -d=*|--public-dns-zone-name=*)
               public_domain="${i#*=}"
               shift # past argument=value
               ;;
          -z=*|--private-dns-zone-name=*)
               dns_zone_name="${i#*=}"
               shift # past argument=value
               ;;
     esac
done
set -- "${POSITIONAL[@]}" # restore positional parameters

# Verify there is an AKV in the RG
akv_name=$(az keyvault list -g "$rg" --query '[0].name' -o tsv)
if [[ -n "$akv_name" ]]
then
    echo "INFO: Azure Key Vault $akv_name found in resource group $rg"
else
    echo "ERROR: no Azure Key Vault found in resource group $rg"
    exit 1
fi

# Find app gateway
appgw_name=$(az network application-gateway list -g "$rg" --query '[0].name' -o tsv)
if [[ -n "$appgw_name" ]]
then
    echo "INFO: Azure Application Gateway $appgw_name found in resource group $rg"
else
    echo "ERROR: no Azure Application Gateway could be found in the resource group $rg"
    exit 1
fi

# Import certs from AKV
fqdn="${appgw_name}.${public_domain}"
cert_name=${fqdn//[^a-zA-Z0-9]/}
echo "Adding SSL certificate to Application Gateway from Key Vault ($cert_sid)..."
# The --keyvault-secret-id parameter doesnt seem to be working in Github's action CLI version (Feb 2021)
# cert_sid=$(az keyvault certificate show -n "$cert_name" --vault-name "$akv_name" --query sid -o tsv)
# az network application-gateway ssl-cert create -n "$cert_name" --gateway-name "$appgw_name" -g "$rg" --keyvault-secret-id "$cert_sid"
pfx_file="/tmp/ssl.pfx"
az keyvault key download -n "$cert_name" --vault-name "$akv_name" --encoding base64 --file "$pfx_file"
cert_passphrase=''
az network application-gateway ssl-cert create -g "$rg" --gateway-name "$appgw_name" -n contoso --cert-file "$pfx_file" --cert-password "$cert_passphrase"

# Import root cert for LetsEncrypt
current_dir=$(dirname "$0")
base_dir=$(dirname "$current_dir")
root_cert_file="${base_dir}/letsencrypt/isrgrootx1.crt"
echo "Adding LetsEncrypt root cert to Application Gateway..."
az network application-gateway root-cert create -g "$rg" --gateway-name "$appgw_name" --name letsencrypt --cert-file "$root_cert_file"