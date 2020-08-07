# Container and Web App networking

This repository contains two sample containers to test microservices applications in Docker and Kubernetes:

* sql api
* web

Note that the images are pretty large, since they are based on standard ubuntu and centos distros. The goal is having a fully functional OS in case any in-container troubleshooting or investigation is required.

* [SQL API](api/README.md)
* [Web](web/README.md)

# Challenges and lab guides

The labs described below include how to deploy these containers in different form factors:

## Challenges

These documents show challenges in an open-ended fashion. They do not contain detailed-instructions or solutions, but just objectives that need to be fulfilled. You will need to do research to find out a valid solution. There might not be a single, unique valid solution, multiple technologies could fulfill the objectives.

* [1. Containers, ACR and ACI](challenges/containers.md)
* [2. AKS network integration](challenges/aks_private.md)
* [3. AKS monitoring](challenges/aks_monitoring.md)
* [4. AKS secrets](challenges/aks_secrets.md)
* [5. Kubernetes security](challenges/aks_security.md)
* [6. Kubernetes Storage](challenges/aks_storage.md)
* [7. Service Mesh](challenges/aks_mesh.md)

## Lab guides

These documents show guided, step-by-step instructions on how to set up certain environments. They are useful if you want to quickly standup an environment without having to do any research:

* [Local Docker](lab-guides/docker.md)
* [Azure Container Instances](lab-guides/aci.md)
* [Azure Kubernetes Service](lab-guides/aks.md)
* [Linux Web App](lab-guides/linux_webapp.md)
* [Windows Web App](lab-guides/windows_webapp.md)
* [Virtual Machines](lab-guides/vms.md)
