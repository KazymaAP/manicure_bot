"""
src/infrastructure/http/health_server.py — HTTP endpoint для health check и мониторинга.

FIXED C-5: добавлена Bearer-токен аутентификация для /metrics.
FIXED H-8: HealthServer слушает 127.0.0.1 вместо 0.0.0.0 для безопасности.
"""
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger = logging.getLogger(__name__)
    logger.warning("aiohttp не установлен. Health server недоступен. Установите: pip install aiohttp")

if TYPE_CHECKING:
    from src.application.services.appointment_service import AppointmentService

logger = logging.getLogger(__name__)


class HealthServer:
    """HTTP сервер для health checks и мониторинга.

    FIXED C-5: /metrics защищён Bearer-токеном (METRICS_TOKEN из .env).
    FIXED H-8: биндится на 127.0.0.1 вместо 0.0.0.0 для предотвращения
    доступа из интернета без файрвола.
    """

    def __init__(
        self,
        appointment_service: "AppointmentService",
        port: int = 8080,
        metrics_token: str | None = None,
        bind_host: str = "127.0.0.1",
    ):
        """Инициализирует health server.

        Args:
            appointment_service: Сервис записей для получения статистики.
            port: Порт для HTTP сервера.
            metrics_token: Bearer-токен для защиты /metrics (METRICS_TOKEN из .env).
            bind_host: IP-адрес для прослушивания (127.0.0.1 по умолчанию для безопасности).
        """
        self.appointment_service = appointment_service
        self.port = port
        # FIXED C-5: токен для /metrics из env (приоритет) или параметра
        self.metrics_token: str | None = os.environ.get("METRICS_TOKEN") or metrics_token
        # FIXED H-8: по умолчанию биндимся только локально
        self.bind_host = bind_host
        self.app = None
        self.runner = None
        self.start_time = datetime.now()

    def _check_metrics_auth(self, request: "web.Request") -> bool:
        """Проверяет Bearer-токен для /metrics.

        FIXED C-5: если METRICS_TOKEN задан — проверяем Authorization: Bearer <token>.
        Если токен не задан в конфигурации — /metrics доступен только с localhost.
        """
        if not self.metrics_token:
            # Токен не настроен — разрешаем только с localhost
            peer = request.remote or ""
            if peer not in ("127.0.0.1", "::1", "localhost"):
                return False
            return True
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[len("Bearer "):].strip()
        return token == self.metrics_token

    async def setup(self) -> None:
        """Настраивает и запускает HTTP сервер."""
        if not HAS_AIOHTTP:
            logger.warning("aiohttp not available, health server disabled")
            return

        self.app = web.Application()
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_get("/metrics", self._handle_metrics)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        # FIXED H-8: биндимся на self.bind_host (127.0.0.1 по умолчанию)
        site = web.TCPSite(self.runner, self.bind_host, self.port)
        await site.start()
        logger.info(
            "Health server started on %s:%d (metrics_auth=%s)",
            self.bind_host, self.port, "token" if self.metrics_token else "localhost-only"
        )

    async def shutdown(self) -> None:
        """Завершает работу HTTP сервера."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health server stopped")

    async def _handle_health(self, request: "web.Request") -> "web.Response":
        """Handler для /health — простой ping (публичный)."""
        return web.json_response(
            {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": int((datetime.now() - self.start_time).total_seconds()),
            }
        )

    async def _handle_metrics(self, request: "web.Request") -> "web.Response":
        """Handler для /metrics — статистика бота (защищена аутентификацией).

        FIXED C-5: проверяем Bearer-токен. Если не авторизован — 401.
        """
        if not self._check_metrics_auth(request):
            return web.json_response(
                {"status": "unauthorized", "message": "Bearer token required for /metrics"},
                status=401,
                headers={"WWW-Authenticate": "Bearer realm=\"metrics\""},
            )
        try:
            import asyncio
            stats = await asyncio.to_thread(self.appointment_service.get_statistics)
            return web.json_response(
                {
                    "status": "ok",
                    "timestamp": datetime.now().isoformat(),
                    "uptime_seconds": int((datetime.now() - self.start_time).total_seconds()),
                    "appointments": {
                        "total": stats.get("total", 0),
                        "active": stats.get("confirmed", 0),
                        "cancelled": stats.get("cancelled", 0),
                        "today": stats.get("today", 0),
                        "week": stats.get("week", 0),
                    },
                }
            )
        except Exception as exc:
            logger.exception("Error in /metrics handler: %s", exc)
            return web.json_response(
                {"status": "error", "message": str(exc)},
                status=500,
            )
