# Demo: cp .env.example .env  then  make demo | make demo-gpu | make demo-gpu-bge
# Compose project root: docker-compose.yml (+ optional deploy/docker-compose.gpu.yml, deploy/docker-compose.gpu-bge.yml)

DOCKER_COMPOSE ?= docker compose
ENV_FILE ?= --env-file .env

COMPOSE_BASE ?= -f docker-compose.yml
COMPOSE_GPU ?= -f docker-compose.yml -f deploy/docker-compose.gpu.yml
COMPOSE_BGE ?= -f docker-compose.yml -f deploy/docker-compose.gpu.yml -f deploy/docker-compose.gpu-bge.yml

.PHONY: demo demo-gpu demo-gpu-bge dev-frontend verify verify-http verify-e2e verify-e2e-gpu verify-e2e-gpu-bge test db-psql db-pgweb-help

demo:
	@test -f .env || (echo "Create .env first: cp .env.example .env" >&2; exit 1)
	$(DOCKER_COMPOSE) $(COMPOSE_BASE) $(ENV_FILE) up -d

demo-gpu:
	@test -f .env || (echo "Create .env first: cp .env.example .env" >&2; exit 1)
	$(DOCKER_COMPOSE) $(COMPOSE_GPU) $(ENV_FILE) up -d

demo-gpu-bge:
	@test -f .env || (echo "Create .env first: cp .env.example .env" >&2; exit 1)
	$(DOCKER_COMPOSE) $(COMPOSE_BGE) $(ENV_FILE) up -d

dev-frontend:
	cd frontend && npm install && npm run dev

verify:
	./scripts/verify_stack.sh

verify-http:
	VERIFY_GATEWAY=1 ./scripts/verify_stack.sh

verify-e2e:
	VERIFY_GATEWAY=1 VERIFY_UPLOAD=1 VERIFY_WORKERS=1 VERIFY_STATUS=1 ./scripts/verify_stack.sh

verify-e2e-gpu:
	VERIFY_GPU=1 VERIFY_GATEWAY=1 VERIFY_UPLOAD=1 VERIFY_WORKERS=1 VERIFY_STATUS=1 ./scripts/verify_stack.sh

verify-e2e-gpu-bge:
	VERIFY_BGE_GPU=1 VERIFY_GATEWAY=1 VERIFY_UPLOAD=1 VERIFY_WORKERS=1 VERIFY_STATUS=1 ./scripts/verify_stack.sh

# 轻量自检（需已 pip install -r requirements.txt，PYTHONPATH=仓库根）
test:
	@cd "$(CURDIR)" && PYTHONPATH=. python3 -m compileall -q gateway core shared services compiler
	@cd "$(CURDIR)" && PYTHONPATH=. python3 -c "from gateway.app import app; print('gateway import ok')"

# 进入 Postgres 交互 SQL（需栈已启动：make demo）
db-psql:
	$(DOCKER_COMPOSE) $(COMPOSE_BASE) $(ENV_FILE) exec -it postgres psql -U contextmap -d contextmap

# 浏览器查看表 / 执行查询（pgweb，端口见 docker-compose.yml）
db-pgweb-help:
	@echo "Pgweb: http://localhost:8088  （docker compose 服务名: pgweb）"
