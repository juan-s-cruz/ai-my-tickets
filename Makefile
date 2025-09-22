# Makefile targets to build the container and run with the necessary options

API_IMAGE_NAME = "ticketing_site"
SERVING_PORT = 8000
PWD = $(shell pwd)

build-ticket-site:
	@cd ticket_system && docker build -f Dockerfile -t $(API_IMAGE_NAME) .

build-ticket-site-no-cache:
	@cd ticket_system && docker build --no-cache -f Dockerfile -t $(API_IMAGE_NAME) .

run_bash:
	@docker run -it --rm --name $(API_IMAGE_NAME) -v $(PWD):/app $(IMAGE_NAME) bash

run_server:
	@docker run -it --rm --name $(API_IMAGE_NAME) --env-file ticket_system/.env -p 127.0.0.1:$(SERVING_PORT):$(SERVING_PORT) -v $(PWD)/ticket_system:/app $(API_IMAGE_NAME)

clean:
	@rm -rf .venv;
	@find . -type d -name "__pycache__" -exec rm -rf {} +;

install_python_env:
	python3 -m venv .venv
	source .venv/bin/activate; pip install --upgrade pip; pip install --no-cache-dir -r ticket_system/requirements.txt