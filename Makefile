.PHONY: docker-up docker-down docker-logs docker-ps docker-build web-build download-geoip build-agent verify test migrate

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api-server

docker-ps:
	docker compose ps

docker-build:
	docker compose build --no-cache

web-build:
	cd web && npm install && npm run build
	cd web-admin && npm run build

download-geoip:
	MAXMIND_LICENSE_KEY="$(MAXMIND_LICENSE_KEY)" ./scripts/download-geoip.sh

build-agent:
	chmod +x ./scripts/package-agent.sh
	./scripts/package-agent.sh

verify:
	chmod +x ./scripts/verify-stack.sh
	./scripts/verify-stack.sh

test:
	cd services/api-server && python3 -m pytest tests/ -v

migrate:
	cd services/api-server && alembic upgrade head
