# Challenge: containers intro

This challenge will cover the basics of containers and a container runtime

## Objectives

You need to fulfill these requirements to complete this challenge:

* Create an Azure Container Registry. Build the SQL API and Web images in this repository and store them in your new ACR
* Deploy the SQL API image in your local machine out of your ACR (you will need a container runtime in your local machine). Deploy a SQL Server as container in your local machine, and make sure that the SQL API can access the SQL container
* Deploy the SQL API image as Azure Container Instance in Azure, deploy an Azure SQL Database and make sure that the API can connect to the database

## Related documentation

These docs might help you achieving these objectives:

* [ACR](https://docs.microsoft.com/azure/container-registry/container-registry-intro)
* [ACI](https://docs.microsoft.com/azure/container-instances/)