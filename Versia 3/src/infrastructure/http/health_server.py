"""
src/infrastructure/http/health_server.py — HTTP endpoint для health check и мониторинга.

Эндпоинты:
  GET /health  — публичный ping (status + uptime)
  GET /metrics — статистика бота, защищена Bearer-токеном

Безопасность:
  - /metrics требует Authorization: Bearer <METRICS_TOKEN>
  - HealthServer биндится только на 127.0.0.1 (не на 0.0.0.0)
  - Если METRICS_TOKEN не задан — /metrics доступен только с localhost
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

if TYPE_CHECKING:
    from src.application.services.appointment_service import AppointmentService

logger = logging.getLogger(__name__)


class HealthServer:
    """HTTP сервер для health checks и мониторинга.

    /health — публичный, возвращает статус и uptime.
    /metrics — защищён Bearer-токеном, возвращает статистику.
    """

    def __init__(
        self,
        appointment_service: AppointmentService,
        port: int = 8080,
        metrics_token: str | None = None,
        bind_host: str = "127.0.0.1",
    ) -> None:
        """Инициализирует health server.

        Args:
            appointment_service: Сервис записей для получения статистики.
            port: Порт для HTTP сервера (по умолчанию 8080).
            metrics_token: Bearer-токен для /metrics (из METRICS_TOKEN в .env).
            bind_host: IP-адрес (127.0.0.1 по умолчанию — только локально).
        """
        self.appointment_service = appointment_service
        self.port = port
        self.metrics_token: str | None = metrics_token
        self.bind_host = bind_host
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self._start_time = datetime.now(tz=timezone.utc)

    def _check_metrics_auth(self, request: web.Request) -> bool:
        """Проверяет Bearer-токен для /metrics.

        Если METRICS_TOKEN задан — проверяем Authorization: Bearer <token> (constant-time).
        Если токен не задан — разрешаем только с localhost.
        """
        if not self.metrics_token:
            peer = request.remote or ""
            return peer in ("127.0.0.1", "::1", "localhost")
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        provided = auth[len("Bearer "):].strip()
        # compare_digest — защита от timing-атак
        return secrets.compare_digest(provided, self.metrics_token)

    async def setup(self) -> None:
        """Настраивает и запускает HTTP сервер."""
        if not HAS_AIOHTTP:
            logger.warning("aiohttp not available — health server disabled. Install: pip install aiohttp")
            return

        self.app = web.Application()
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_get("/metrics", self._handle_metrics)
        # Запрет неизвестных методов
        self.app.router.add_route("*", "/{path_info:.*}", self._handle_not_found)

        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.bind_host, self.port)
        await site.start()
        logger.info(
            "Health server started on %s:%d (metrics_auth=%s)",
            self.bind_host,
            self.port,
            "token" if self.metrics_token else "localhost-only",
        )

    async def shutdown(self) -> None:
        """Завершает работу HTTP сервера."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health server stopped")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handler для GET /health — публичный ping."""
        now = datetime.now(tz=timezone.utc)
        uptime = int((now - self._start_time).total_seconds())
        return web.json_response(
            {
                "status": "ok",
                "timestamp": now.isoformat(),
                "uptime_seconds": uptime,
            }
        )

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Handler для GET /metrics — статистика, защищена аутентификацией."""
        if not self._check_metrics_auth(request):
            return web.json_response(
                {"status": "unauthorized", "message": "Bearer token required for /metrics"},
                status=401,
                headers={"WWW-Authenticate": 'Bearer realm="metrics"'},
            )
        try:
            # FIX #15: таймаут 5с на получение статистики — предотвращает зависание /metrics
            try:
                stats = await asyncio.wait_for(
                    asyncio.to_thread(self.appointment_service.get_statistics),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                stats = {"error": "timeout", "total": 0, "confirmed": 0,
                         "cancelled": 0, "today": 0, "week": 0}
            now = datetime.now(tz=timezone.utc)
            uptime = int((now - self._start_time).total_seconds())
            return web.json_response(
                {
                    "status": "ok",
                    "timestamp": now.isoformat(),
                    "uptime_seconds": uptime,
                    "appointments": {
                        "total": stats.get("total", 0),
                        "active": stats.get("confirmed", 0),
                        "cancelled": stats.get("cancelled", 0),
                        "today": stats.get("today", 0),
                        "week": stats.get("week", 0),
                    },
                }
            )
        except Exception:
            logger.exception("Error in /metrics handler")
            return web.json_response(
                {"status": "error", "message": "Internal server error"},
                status=500,
            )

    @staticmethod
    async def _handle_not_found(request: web.Request) -> web.Response:
        """Handler для неизвестных путей."""
        return web.json_response({"status": "not_found"}, status=404)
