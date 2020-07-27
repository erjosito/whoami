# Container and Web App networking

This repository contains two sample containers to test microservices applications in Docker and Kubernetes:

* sql api
* web

Note that the images are pretty large, since they are based on standard ubuntu and centos distros. The goal is having a fully functional OS in case any in-container troubleshooting or investigation is required.

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

# Challenges and lab guides

The labs described below include how to deploy these containers in different form factors:

## Challenges

These documents show challenges in an open-ended fashion. They do not contain detailed-instructions or solutions, but just objectives that need to be fulfilled. You will need to do research to find out a valid solution. There is not a single valid solution, often multiple technologies can fulfill the objectives.

* [1. Containers, ACR and ACI](challenges/containers.md)
* [2. AKS network integration](challenges/aks_private.md)
* [3. AKS monitoring](challenges/aks_monitoring.md)
* [4. AKS secrets](challenges/aks_secrets.md)
* [5. Kubernetes security](challenges/aks_security.md)
* [6. Service Mesh](challenges/aks_mesh.md)

## Lab guides

These documents show guided, step-by-step instructions on how to set up certain environments. They are useful if you want to quickly standup an environment without having to do any research:

* [Local Docker][lab-guides/docker.md]
* [Azure Container Instances][lab-guides/aci.md]
* [Azure Kubernetes Service][lab-guides/aks.md]
* [Linux Web App][lab-guides/linux_webapp.md]
* [Windows Web App][lab-guides/windows_webapp.md]
* [Virtual Machines][lab-guides/vms.md]
