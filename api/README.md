# SQL API Container

Here you can find the source files to build this container. You can build it locally with:

```bash
docker build -t sqlapi:1.0 .
```

or in a registry such as Azure Container Registry with:

```bash
az acr build -r <your_acr_registry> -g <your_azure_resource_group> -t sqlapi:1.0 .
```

The container is a web API with the following endpoints:

* `/api/healthcheck`: returns a basic JSON code to verify if the container is running
* `/api/sqlversion`: returns the results of a SQL query (`SELECT @@VERSION` for SQL Server or `SELECT VERSION();` for MySQL/Postgres) against a SQL database. You can override the value of the `SQL_SERVER_FQDN` via a query parameter 
* `/api/sqlsrcip`: returns the results of a SQL query (`SELECT CONNECTIONPROPERTY("client_net_address")` for SQL Server, `SELECT host FROM information_schema.processlist WHERE ID=connection_id();` for MySQL or `SELECT inet_client_addr ();` for Postgres) against a SQL database. You can override the value of the `SQL_SERVER_FQDN`, `SQL_SERVER_USERNAME`, `SQL_SERVER_PASSWORD` and `SQL_SERVER_ENGINE` via a query parameter
* `/api/ip`: returns information about the IP configuration of the container, such as private IP address, egress public IP address, default gateway, DNS servers, etc
* `/api/dns`: returns the IP address resolved from the FQDN supplied in the parameter `fqdn`
* `/api/printenv`: returns the environment variables for the container
* `/api/curl`: returns the output of a curl request, you can specify the argument with the parameter `url`

The container requires thses environment variables :

* `SQL_SERVER_FQDN`: FQDN of the SQL server
* `SQL_SERVER_DB` (optional): FQDN of the SQL server
* `SQL_SERVER_USERNAME`: username for the SQL server
* `SQL_SERVER_PASSWORD`: password for the SQL server
* `SQL_ENGINE`: can be either `sqlserver`, `mysql` or `postgres`
* `PORT` (optional): TCP port where the web server will be listening (8080 per default)

Note that environment variables can also be injected as files in the `/secrets` directory.