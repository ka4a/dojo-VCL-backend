# VCL ![ci](https://github.com/reustleco/dojo-VCL-backend/actions/workflows/vcl-ci.yml/badge.svg)
Virtual Coding Lab is a Modern Cloud IDE.

# Development setup

## Prerequisites
1. Make
   1. (on mac via homebrew: `brew install make`)
2. Docker
3. DockerCompose
4. Minikube (Version>= v1.25)
   1. (on mac via homebrew: `brew install minikiube`)
5. A functioning Kubernetes cluster (`~/.kube/config` is used with current context by default)
6. [Helm](https://helm.sh/ru/docs/intro/install/)

## Project Installation
### Install pre-requisites
VCL runs the following service containers:
1. Kubernetes - web server
2. Kubernetes - celery
3. Kubernetes - celery beat
4. Kubernetes - consumer
5. Kubernetes - workspace watcher
6. Kubernetes - workspace supervisor
7. Kubernetes - traefik as ingress controller
8. Docker Compose - redis
9. Docker Compose - postgres
10. Docker Compose - rabbitmq

## Setup locally

### Minikube Cluster
```bash
# If you're on MBP M1 follow installation steps below OR
# follow instructions for other platforms @
# https://minikube.sigs.k8s.io/docs/start/

# Install minikube binariess (M1)
$ curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-darwin-arm64
$ sudo install minikube-darwin-arm64 /usr/local/bin/minikube

# Configure and start the minikube cluster
$ make minikube-init

# Open a terminal tab and run following to start proxy access to services.
$ sudo minikube tunnel

# Minikube comes with a nice dashboard that lets you see the state of cluster intuitively.
$ minikube dashboard --url

🤔  Verifying dashboard health ...
🚀  Launching proxy ...
🤔  Verifying proxy health ...
URL: http://127.0.0.1:57298/api/v1/namespaces/kubernetes-dashboard/services/http:kubernetes-dashboard:/proxy/
```

### Environment override
Add `values-minikube-overrides.yaml` into `./charts/vcl-core/envs` OR `./charts/vcl-workspace/envs`. These are used when we need to override values that are coming from  `values-minikube.yaml`.

### Build and cache local images
If you make changes to the apps and want to update the images loaded in minikube, (e.g. you upgraded dependencies), use:
- `make images-minikube-build`

### Setup tunnels
Run `sudo minikube tunnel` to expose K8s services.

In order to make tunnel work with the development environment, we will need to override `ingressHost` to point to our tunnel's hostname. For example:
```yaml
# file: ./charts/vcl-core/envs/values-minikube-overrides.yaml
ingressHost: dojoide.ngrok.io
```
If you are already running the app, redeploy the updated values into cluster through `make k8s-restart`.

## Run the application
By default, `make up` will run the app locally against minikube.

It uses the following commands:
- `helm upgrade vcl-core ./charts -f ./charts/vcl-core/envs/values-minikube.yaml -f ./charts/vcl-core/envs/values-minikube-overrides.yaml -i`
- `helm upgrade vcl-workspace ./charts -f ./charts/vcl-workspace/envs/values-minikube.yaml -f ./charts/vcl-workspace/envs/values-minikube-overrides.yaml -i`

### Install the git hook scripts
run `pre-commit install` to set up the git hook scripts which lets you prettify your
code and fix flake8 violations(if any) before you could commit your code.
```
$ pip3 install pre-commit  # https://github.com/pre-commit/pre-commit
$ pre-commit install
pre-commit installed at .git/hooks/pre-commit
```
now pre-commit will run automatically on git commit!

### Useful commands
```bash
# To start local dev environment
make up
# To check application logs
make logs
# To stop local dev environment
make stop

# Now, http://localhost/swagger should have the development server running.
```

## Admin Panel
Django admin is running at: http://localhost/admin, You can setup superuser account for yourself by running following:
```bash
make setup_superuser
```
Now, you can use the following credentials to log into Django Admin panel:
```
Username: admin
Password: admin
```

## RabbitMQ Admin Dashboard

Available at http://localhost:15672/#/ , username and password are `guest`

## Swagger API Docs
Swagger API docs are located at http://localhost/swagger, you should be able to try some APIs there.

## Debug
Django Debug Toolbar @ http://localhost/__debug__

## Configure an LTI Consumer and Tool on your localhost
Instructions are similar to the [Django example for PyLTI1.3](https://github.com/dmitry-viskov/pylti1.3-django-example) excempt that instead of json configurations we configure the LTI settings using the Django Admin ([as per instructions](https://github.com/dmitry-viskov/pylti1.3#configuration-using-django-admin-ui)).

- On the edX Django admin, make sure "Allow PII sharing" is enabled for the course (`admin/lti_consumer/courseallowpiisharinginltiflag/`)
- Use `localtunnel` or similar to expose your Django endpoints e.g. `lt --port 80 --subdomain custom-domain`
- Add and configure an LTI Consumer xBlock with the right urls and settings:
  - Tool launch url: `https://custom-domain.loca.lt/lti/launch/`
  - Tool Initiate Login URL: `https://custom-domain.loca.lt/lti/login/`
  - Deep Linking Launch URL: `https://custom-domain.loca.lt/lti/launch/`
  - LTI Assignment and Grades Service: Programmatic
  - Tool public key: add the key generated in previous step
  - LTI Launch Target: New Window
  - Set all flags except "Hide External Tool" to True
- Create a keypair on the VCL Django admin at `/admin/lti1p3_tool_config/ltitoolkey/`
- Create an LTI configuration on the VCL Django admin at `https://custom-domain.loca.lt/admin/lti1p3_tool_config/ltitool/` using the xBlock urls from Studio

## How to generate LTI keys

You need to run the next command in your terminal to get public and private keys that will be stored in your LTI configuration.

```bash
ssh-keygen -t rsa -b 4096 -m PEM -f jwtRS256.key
# Don't add passphrase
openssl rsa -in jwtRS256.key -pubout -outform PEM -out jwtRS256.key.pub
cat jwtRS256.key
cat jwtRS256.key.pub
```

## Deploy

### Build and push images
Images are built and pushed to ECS via CI, with the `build-push-ecr.yml` pipeline. Migrations are run in a k8s job as part of helm pre-install/pre-upgrade hook.

#### Authenticate in AWS
- `aws ecr --profile vcl_ecr_pusher get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin $REGISTRY`

### Use helm to deploy

#### Authenticate in EKS
```
export AWS_DEFAULT_REGION=ap-northeast-1
export AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
aws eks --region ap-northeast-1 update-kubeconfig --name vcl-core-dev
```
#### Deploy
In order to deploy to staging, you will need to specify a dedicated variables file:
`helm upgrade vcl-stage ./charts -f ./charts/envs/values-staging.yaml -i`

To specify which version of the various Docker images to deploy, add `--set imageTag=$version`:
`helm upgrade vcl-stage ./charts -f ./charts/envs/values-staging.yaml -i --set imageTag=latest`

#### Useful commands
- Check deployment status: `helm ls`
- Switch to local minikube: `minikube update-context`
- Get main cluster endpoint: `kubectl get service`
### Useful make targets

```bash
# start services
make up

# start services in detached mode
make up-d

# restart the service containers
make restart

# see web logs
make logs

# see celery logs
make clogs

# attach to python shell
make shell

# ssh into web service container
make ssh

# ssh into celery service container
make cssh

# generate migrations
make migrations

# apply migrations
make migrate

# install requirements
make requirements

# run tests
make test

# run lint i.e. flake8
make flake8

# stop services
make stop

# remove service containers
make down
```

## Test

### E2E

To run E2E test locally you need to have

1. A working minikube k8s cluster
2. Two localtunnels
   1. vcl-core chart deployment – for VCL web service
   2. mock-lti-consumer container running flask web server

Create .env file containing following contents:
```
# filename .env
WEB_ADDRESS=dojoide.ngrok.io  # VCL web service address
MOCK_LTI_CONSUMER_ADDRESS=lti-mock-server.ngrok.io  # mock-lti-consumer web server address
```
Load these env variables into shell:
```bash
$ export $( grep -vE "^(#.*|\s*)$" .env )
```

Now, setup E2E tests environment
```bash
# Start E2E environment
$ make test-env-start

# Run E2E tests
$ make e2e

# Stop E2E environment
$ make test-env-stop
```
This executes all tests that are placed in tests/e2e folder and you will see corresponding results.

### Mock LTI Consumer

To test VCL application we developed a [mock server](./mock-lti-consumer). Mock server is a flask server that handles
requests from VCL backend and provides LTI handshake capabilities. Using mock server you don't need to have EDX platform for that you need to setup a proper LTI tool configuration using private and public keys that placed in
[mock server](./mock-lti-consumer). In the future a db fixture will be added to configure LTI tool automatically.
You can spin up the mock server using the next makefile targets:

```bash
# builds a mock server
make build-mock
```

This service can be found in [docker-compose.test.yaml](./docker-compose.test.yaml)
