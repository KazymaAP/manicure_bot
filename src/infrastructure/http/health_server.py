"""
src/infrastructure/http/health_server.py — HTTP endpoint для health check и мониторинга.

FIXED: aiohttp сервер с /health endpoint для Uptime Robot / Grafana.
"""
import logging
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
    """HTTP сервер для health checks и мониторинга."""

    def __init__(self, appointment_service: "AppointmentService", port: int = 8080):
        """Инициализирует health server.

        Args:
            appointment_service: Сервис записей для получения статистики.
            port: Порт для HTTP сервера.
        """
        self.appointment_service = appointment_service
        self.port = port
        self.app = None
        self.runner = None
        self.start_time = datetime.now()

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
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("Health server started on port %d", self.port)

    async def shutdown(self) -> None:
        """Завершает работу HTTP сервера."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health server stopped")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handler для /health — простой ping."""
        return web.json_response(
            {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": int((datetime.now() - self.start_time).total_seconds()),
            }
        )

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Handler для /metrics — статистика бота."""
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
