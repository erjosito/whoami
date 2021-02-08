#!/bin/bash
az account show
echo "Received values from certbot:"
echo " - CERTBOT_VALIDATION: $CERTBOT_VALIDATION"
echo " - CERTBOT_DOMAIN:     $CERTBOT_DOMAIN"
# Try first to find the whole domain as an Azure DNS zone
DNS_ZONE_NAME=$CERTBOT_DOMAIN
echo "Finding out resource group for DNS zone $DNS_ZONE_NAME..."
DNS_ZONE_RG=$(az network dns zone list --query "[?name=='$DNS_ZONE_NAME'].resourceGroup" -o tsv)
# If none was found, try stripping the hostname
if [[ -z "$DNS_ZONE_RG" ]]
then
    DNS_ZONE_NAME=$(expr match "$CERTBOT_DOMAIN" '.*\.\(.*\..*\)')
    echo "Finding out resource group for DNS zone $DNS_ZONE_NAME..."
    DNS_ZONE_RG=$(az network dns zone list --query "[?name=='$DNS_ZONE_NAME'].resourceGroup" -o tsv)
fi
echo " - DNS ZONE:           $DNS_ZONE_NAME"
echo " - DNS RG:             $DNS_ZONE_RG"
SUFFIX=".${DNS_ZONE_NAME}"
RECORD_NAME=_acme-challenge.${CERTBOT_DOMAIN%"$SUFFIX"}
echo "Creating record $RECORD_NAME in DNS zone $DNS_ZONE_NAME..."
az network dns record-set txt create -n "$RECORD_NAME" -z "$DNS_ZONE_NAME" -g $DNS_ZONE_RG --ttl 30
az network dns record-set txt add-record -n "$RECORD_NAME" -z "$DNS_ZONE_NAME" -g "$DNS_ZONE_RG" -v "$CERTBOT_VALIDATION"
