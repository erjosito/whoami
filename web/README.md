# Web frontend for SQL API

Simple PHP web page that can access the [SQL API](../api/README.md). You can build it locally with:

```bash
docker build -t web:1.0 .
```

or in a registry such as Azure Container Registry with:

```bash
az acr build -r <your_acr_registry> -g <your_azure_resource_group> -t web:1.0 .
```

Alternative, it is available in dockerhub [here](https://hub.docker.com/repository/docker/erjosito/whomai)).

The container require these environment variables:

* `API_URL`: URL where the SQL API can be found, for example `http://1.2.3.4:8080`
