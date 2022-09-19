IMAGE_PREFIX ?= vcl
TAG ?= latest
REGISTRY ?=
SCHEME ?= https
WEB_DOMAIN ?= example.loca.lt
WEB_ADDRESS ?= ${SCHEME}://${WEB_DOMAIN}
# Namespace to pass to the various commands
NS ?= default
MOCK_LTI_CONSUMER_ADDRESS ?= https://example-mock.loca.lt

# build docker images with specific prefix IMAGE_PREFIX with specific $TAG.
# It uses $REGISTRY with / in the end
image-minikube-build:
	@eval $$(minikube docker-env);
	docker build . -f ./vcl/Dockerfile -t ${REGISTRY}${IMAGE_PREFIX}_web:${TAG} \
									   -t ${REGISTRY}${IMAGE_PREFIX}_celery:${TAG} \
									   -t ${REGISTRY}${IMAGE_PREFIX}_beat:${TAG};
	docker build . -f ./consumer/Dockerfile -t ${REGISTRY}${IMAGE_PREFIX}_consumer:${TAG}; \
	docker build . -f ./k8s-watcher/Dockerfile -t ${REGISTRY}${IMAGE_PREFIX}_watcher:${TAG}; \
	docker build . -f ./init-container/Dockerfile -t ${REGISTRY}${IMAGE_PREFIX}_init_container:${TAG}; \
	docker build . -f ./ws-supervisor/Dockerfile -t ${REGISTRY}${IMAGE_PREFIX}_ws_supervisor:${TAG};

e2e-install-requirements:
	pip3 install -r test/e2e/requirements.txt

e2e:
	WEB_ADDRESS=${WEB_ADDRESS} EDX_PLATFORM_ADDRESS=${MOCK_LTI_CONSUMER_ADDRESS} python3 -m unittest test/e2e/workspace.py

truncate-db:
	$(eval ENV=$(shell kubectl exec -n ${NS} -ti deploy/web -- sh -c "echo \$${ENVIRONMENT}"))
	if [ "${ENV}" != "TESTING" ] && [ "${ENV}" != "DEV" ]; \
	then \
		echo "This target can be executed only for TESTING or DEV environments"; \
		exit 1; \
	fi
	kubectl exec -n ${NS} deploy/web -- /bin/sh -c "PYTHONWARNINGS=ignore python manage.py flush --no-input"

purge-queues:  # This purges redis cache, rabbitmq consumer queue and celery queue.
	kubectl exec -ti -n ${NS} deploy/web -- python manage.py purge_queues

# push to registry with specific tag and image prefix
image-push:
	@eval $$(minikube docker-env); \
	docker push ${REGISTRY}${IMAGE_PREFIX}_web:${TAG}; \
	docker push ${REGISTRY}${IMAGE_PREFIX}_celery:${TAG}; \
	docker push ${REGISTRY}${IMAGE_PREFIX}_beat:${TAG}; \
	docker push ${REGISTRY}${IMAGE_PREFIX}_consumer:${TAG}; \
	docker push ${REGISTRY}${IMAGE_PREFIX}_watcher:${TAG}; \
	docker push ${REGISTRY}${IMAGE_PREFIX}_init_container:${TAG}; \
	docker push ${REGISTRY}${IMAGE_PREFIX}_ws_supervisor:${TAG}; \

minikube-load-%:
	minikube image load ${REGISTRY}${IMAGE_PREFIX}_$*:${TAG}
	@echo "loaded ${REGISTRY}${IMAGE_PREFIX}_$*:${TAG} into minikube"

# Used to push images from a registry to minikube
minikube-load:
	$(MAKE) minikube-load-celery
	$(MAKE) minikube-load-beat
	$(MAKE) minikube-load-consumer
	$(MAKE) minikube-load-watcher
	$(MAKE) minikube-load-init_container
	$(MAKE) minikube-load-ws_supervisor
	$(MAKE) minikube-load-web

minikube-init:
	@eval $$(minikube docker-env); \
	minikube start --mount-string="${PWD}:/vcl" --mount-gid='www-data' --mount-uid='www-data' --mount
	$(MAKE) image-minikube-build

dump-fixture:
	kubectl exec -n ${NS} -ti deploy/web -- /bin/sh -c "PYTHONWARNINGS=ignore python manage.py dumpdata \
	-e admin.logentry \
	-e sessions.session \
	-e django_celery_results.taskresult \
	-e auth.User \
	-e auth \
	-e contenttypes \
	-e django_celery_beat \
	-e assignment.workspacesession \
	--format json --indent 2 > assignment/management/commands/fixture.json"

load-e2e-fixture:
	kubectl exec -n ${NS} deploy/web -- /bin/sh -c "PYTHONWARNINGS=ignore python manage.py load_e2e_fixture ${MOCK_LTI_CONSUMER_ADDRESS}"

build-mock:
	docker build -t mock_lti_consumer:latest mock-lti-consumer

minikube-restart:
	minikube stop
	$(MAKE) minikube-init

deploy-vcl-core-staging:
	helm upgrade -i vcl-stg ./charts/vcl-core -f charts/vcl-core/envs/values-staging.yaml --set djangoSecret="${DJANGO_SECRET_KEY}" --set workspace.defaultVscodePassword="${VSCODE_PASSWORD}" --set workspace.githubAccessToken="${GH_ACCESS_TOKEN}" --set imageTag="${TAG}" --namespace vcl-core

deploy-vcl-workspace-staging:
	helm upgrade -i vcl-stg ./charts/vcl-workspace -f charts/vcl-workspace/envs/values-staging.yaml --set imageTag="${TAG}" --namespace vcl-core

rollback-staging:
	helm rollback vcl-stg --namespace vcl-core

deploy-vcl-core-testing:
	helm upgrade -i vcl-test ./charts/vcl-core -f charts/vcl-core/values.yaml -f charts/vcl-core/envs/values-testing.yaml --set djangoSecret="${DJANGO_SECRET_KEY}" --set workspace.defaultVscodePassword="${VSCODE_PASSWORD}" --set imageTag="${TAG}" --namespace vcl-core

deploy-vcl-workspace-testing:
	helm upgrade -i vcl-test ./charts/vcl-workspace -f charts/vcl-workspace/envs/values-testing.yaml --set imageTag="${TAG}" --namespace vcl-core

rollback-testing:
	helm rollback vcl-test --namespace vcl-core

setup-traefik:
	helm repo add traefik https://helm.traefik.io/traefik
	helm dependency build ./charts/vcl-core

build:
	docker-compose build

docker-up:
	docker-compose up --remove-orphans

docker-up-d:
	docker-compose up -d --remove-orphans

docker-down:
	docker-compose down

docker-restart:
	docker-compose restart

k8s-up: setup-traefik
	@helm upgrade vcl-core ./charts/vcl-core -f ./charts/vcl-core/envs/values-minikube.yaml -f ./charts/vcl-core/envs/values-minikube-overrides.yaml -i
	@helm upgrade vcl-workspace ./charts/vcl-workspace -f ./charts/vcl-workspace/envs/values-minikube.yaml -f ./charts/vcl-workspace/envs/values-minikube-overrides.yaml -i

k8s-down:
	@helm del vcl-core
	@helm del vcl-workspace

k8s-restart:
	@helm upgrade vcl-core ./charts/vcl-core -f ./charts/vcl-core/envs/values-minikube.yaml -f ./charts/vcl-core/envs/values-minikube-overrides.yaml
	@helm upgrade vcl-workspace ./charts/vcl-workspace -f ./charts/vcl-workspace/envs/values-minikube.yaml -f ./charts/vcl-workspace/envs/values-minikube-overrides.yaml

up: k8s-up docker-up

up-d: k8s-up docker-up-d

stop:
	docker-compose stop

restart: k8s-restart docker-restart

down: k8s-down docker-down

mock-logs:
	docker logs -f vcl.test.mock_lti_consumer

logs:
	make -j 5 wlogs clogs blogs rlogs watcher-logs

wlogs:
	kubectl logs deploy/web -f --tail=500 -n ${NS}

clogs:
	kubectl logs deploy/celery -f --tail=500 -n ${NS}

blogs:
	kubectl logs deploy/beat -f --tail=500 -n ${NS}

rlogs:
	kubectl logs deploy/consumer -f --tail=500 -n ${NS}

watcher-logs:
	kubectl logs deploy/watcher -f --tail=500 -n ${NS}

ssh:
	kubectl exec -it deploy/web -- /bin/bash

cssh:
	kubectl exec -it deploy/celery -- /bin/bash

wssh:
	kubectl exec -it deploy/watcher -- /bin/bash

shell:
	kubectl exec -it deploy/web -- /bin/bash -c "python manage.py shell_plus"

migrations:
	kubectl exec -it deploy/web -- /bin/bash -c "python manage.py makemigrations"

migrate:
	kubectl exec -it deploy/web -- /bin/bash -c "python manage.py migrate"

requirements:
	kubectl exec -it deploy/web -- /bin/bash -c "pip install --disable-pip-version-check --exists-action w -r requirements/core.txt -r requirements/dev.txt"

setup_superuser:
	kubectl exec -it -n ${NS} deploy/web -- /bin/bash -c "python manage.py createsuperuser --verbosity 3"

test:
	kubectl exec -it deploy/web -- /bin/bash -c "python manage.py test"

flake8:
	kubectl exec -it deploy/web -- /bin/bash -c "flake8 --ignore=E999 --max-line-length=120 --exclude core/tests,core/migrations"

# TODO: Remove the `hotreload` make target once hot-reloading is implemented into all the services.
hotreload:
	kubectl rollout restart deploy/beat deploy/celery deploy/consumer deploy/watcher -n ${NS}

test-k8s-start:
	-kubectl create ns test
	@helm upgrade test-vcl-core ./charts/vcl-core -f ./charts/vcl-core/envs/values-local-test.yaml --set ingressHost="${WEB_DOMAIN}" --set ingressProtocol="${SCHEME}"  -i --namespace test

test-k8s-stop:
	@helm del test-vcl-core -n test

test-docker-start:
	WEB_ADDRESS=${WEB_ADDRESS} MOCK_LTI_CONSUMER_ADDRESS=${MOCK_LTI_CONSUMER_ADDRESS} docker-compose -p test-vcl -f docker-compose.test.yaml up --build -d --remove-orphans

test-docker-stop:
	docker-compose -p test-vcl -f docker-compose.test.yaml stop

test-docker-down:
	docker-compose -p test-vcl -f docker-compose.test.yaml down -v

test-env-start: test-docker-start test-k8s-start

test-env-stop: test-k8s-stop test-docker-stop

test-env-down:
	-$(MAKE) test-k8s-stop
	-$(MAKE) test-docker-down
