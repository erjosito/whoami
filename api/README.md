# SQL API Container

Here you can find the source files to build this container. You can build it locally with:

```bash
docker build -t sqlapi:1.0 .
```

or in a registry such as Azure Container Registry with:

```bash
az acr build -r <your_acr_registry> -g <your_azure_resource_group> -t sqlapi:1.0 .
```

Alternative, sql-api is available in dockerhub [here](https://hub.docker.com/repository/docker/erjosito/sqlapi)).

The container is a web API with the following endpoints:

* `/api/healthcheck`: returns a basic JSON code
* `/api/sqlversion`: returns the results of a SQL query (`SELECT @@VERSION`) against a SQL database. You can override the value of the `SQL_SERVER_FQDN` via a query parameter 
* `/api/sqlsrcip`: returns the results of a SQL query (`SELECT CONNECTIONPROPERTY("client_net_address")`) against a SQL database. You can override the value of the `SQL_SERVER_FQDN` via a query parameter
* `/api/ip`: returns information about the IP configuration of the container, such as private IP address, egress public IP address, default gateway, DNS servers, etc
* `/api/dns`: returns the IP address resolved from the FQDN supplied in the parameter `fqdn`
* `/api/printenv`: returns the environment variables for the container
* `/api/curl`: returns the output of a curl request, you can specify the argument with the parameter `url`
* `/api/mysql`: queries a MySQL database. It uses the same environment variables as the SQL Server endpoints, and you can override them with query parameters

The container requires thses environment variables :

* `SQL_SERVER_FQDN`: FQDN of the SQL server
* `SQL_SERVER_DB` (optional): FQDN of the SQL server
* `SQL_SERVER_USERNAME`: username for the SQL server
* `SQL_SERVER_PASSWORD`: password for the SQL server
* `PORT` (optional): TCP port where the web server will be listening (8080 per default)

Note that environment variables can also be injected as files in the `/secrets` directory.