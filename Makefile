infra-up:
	@echo "--- 启动文件服务 ---"
	docker compose -f deploy/registeries/docker-compose.yaml up -d
	docker compose -f deploy/cloud_init/docker-compose.yaml up -d

app-up:
	@echo "--- 启动 MCP 和监控 ---"
	docker compose -f src/monitoring/docker-compose.yaml up -d --build

clean:
	@echo "--- 停止所有服务 ---"
	docker compose -f deploy/registeries/docker-compose.yaml down
	docker compose -f deploy/cloud_init/docker-compose.yaml down
	docker compose -f src/monitoring/docker-compose.yaml down