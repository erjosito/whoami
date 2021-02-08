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
fqdn="*.${public_domain}"
cert_name=${fqdn//[^a-zA-Z0-9]/}
cert_id=$(az network application-gateway ssl-cert show -n "$cert_name" --gateway-name "$appgw_name" --query id -o tsv)
if [[ -z "$cert_id" ]]
then
    echo "Adding SSL certificate to Application Gateway from Key Vault..."
    # The --keyvault-secret-id parameter doesnt seem to be working in Github's action CLI version (Feb 2021)
    # cert_sid=$(az keyvault certificate show -n "$cert_name" --vault-name "$akv_name" --query sid -o tsv)
    # az network application-gateway ssl-cert create -n "$cert_name" --gateway-name "$appgw_name" -g "$rg" --keyvault-secret-id "$cert_sid"
    pfx_file="/tmp/ssl.pfx"
    az keyvault secret download -n "$cert_name" --vault-name "$akv_name" --encoding base64 --file "$pfx_file"
    cert_passphrase=''
    az network application-gateway ssl-cert create -g "$rg" --gateway-name "$appgw_name" -n "$cert_name" --cert-file "$pfx_file" --cert-password "$cert_passphrase" -o none
else
    echo "Cert $cert_name already exists in application gateway $appgw_name"
fi

# Import root cert for LetsEncrypt
root_cert_id=$(az network application-gateway ssl-cert show -n letsencrypt --gateway-name "$appgw_name" --query id -o tsv)
if [[ -z "$root_cert_id" ]]
then
    current_dir=$(dirname "$0")
    base_dir=$(dirname "$current_dir")
    root_cert_file="${base_dir}/letsencrypt/isrgrootx1.crt"
    echo "Adding LetsEncrypt root cert to Application Gateway..."
    az network application-gateway root-cert create -g "$rg" --gateway-name "$appgw_name" --name letsencrypt --cert-file "$root_cert_file" -o none
else
    echo "LetsEncrypt root certificate already present in Application Gateway $appgw_name"
fi

# HTTP Settings and probe
echo "Creating probe and HTTP settings..."
az network application-gateway probe create -g "$rg" --gateway-name "$appgw_name" \
  --name aciprobe --protocol Https --host-name-from-http-settings --match-status-codes 200-399 --port 443 --path /api/healthcheck -o none
az network application-gateway http-settings create -g "$rg" --gateway-name "$appgw_name" --port 443 \
  --name acisettings --protocol https --host-name-from-backend-pool --probe aciprobe --root-certs letsencrypt -o none

# Create config for production container
echo "Creating config for production ACIs..."
az network application-gateway address-pool create -n aciprod -g "$rg" --gateway-name "$appgw_name" \
  --servers "api-prod-01.${dns_zone_name}" -o none
frontend_name=$(az network application-gateway frontend-ip list -g "$rg" --gateway-name "$appgw_name" --query '[0].name' -o tsv)
az network application-gateway frontend-port create -n aciprod -g "$rg" --gateway-name "$appgw_name" --port 443 -o none
az network application-gateway http-listener create -n aciprod -g "$rg" --gateway-name "$appgw_name" \
  --frontend-port aciprod --frontend-ip "$frontend_name" --ssl-cert "$cert_name" -o none
az network application-gateway rule create -g "$rg" --gateway-name "$appgw_name" -n aciprod \
  --http-listener aciprod --rule-type Basic --address-pool aciprod --http-settings acisettings -o none

# Create config for dashboard
echo "Creating config for dashboard..."
dash_ip=$(az container show -n dash -g "$rg" --query 'ipAddress.ip' -o tsv) && echo "$dash_ip"
az network application-gateway probe create -g "$rg" --gateway-name "$appgw_name" \
  --name dash --protocol Http --host-name-from-http-settings --match-status-codes 200-399 --port 8050 --path / -o none
az network application-gateway http-settings create -g "$rg" --gateway-name "$appgw_name" --port 443 \
  --name dash --protocol http --host-name-from-backend-pool --probe dash -o none
az network application-gateway address-pool create -n dash -g "$rg" --gateway-name "$appgw_name" --servers "$dash_ip" -o none
frontend_name=$(az network application-gateway frontend-ip list -g "$rg" --gateway-name "$appgw_name" --query '[0].name' -o tsv)
az network application-gateway frontend-port create -n dash -g "$rg" --gateway-name "$appgw_name" --port 8050 -o none
az network application-gateway http-listener create -n dash -g "$rg" --gateway-name "$appgw_name" \
  --frontend-port dash --frontend-ip "$frontend_name" --ssl-cert "$cert_name" -o none
az network application-gateway rule create -g "$rg" --gateway-name "$appgw_name" -n dash \
  --http-listener dash --rule-type Basic --address-pool dash --http-settings dash -o none

# Cleanup initial dummy config
az network application-gateway rule delete -g "$rg" --gateway-name "$appgw_name" -n rule1 -o none
az network application-gateway address-pool delete -g "$rg" --gateway-name "$appgw_name" -n appGatewayBackendPool -o none
az network application-gateway http-settings delete -g "$rg" --gateway-name "$appgw_name" -n appGatewayBackendHttpSettings -o none
az network application-gateway http-listener delete -g "$rg" --gateway-name "$appgw_name" -n appGatewayHttpListener -o none
