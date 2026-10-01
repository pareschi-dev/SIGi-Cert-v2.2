from __future__ import annotations

import asyncio

import httpx


class HCaptchaSolver:
    BASE_URL = "https://2captcha.com"

    def __init__(self, api_key: str | None = None, timeout: int = 120, polling: int = 5):
        self.api_key = api_key or ""
        self.timeout = timeout
        self.polling = polling

    async def resolver(self, sitekey: str, pageurl: str) -> str:
        if not self.api_key:
            return "SIMULATED_HCAPTCHA_TOKEN"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.BASE_URL}/in.php",
                data={
                    "key": self.api_key,
                    "method": "hcaptcha",
                    "sitekey": sitekey,
                    "pageurl": pageurl,
                    "json": 1,
                },
            )
            data = response.json()
            if data.get("status") != 1:
                raise RuntimeError(f"2Captcha erro: {data.get('request')}")

            captcha_id = data["request"]
            start = asyncio.get_running_loop().time()
            while (asyncio.get_running_loop().time() - start) < self.timeout:
                await asyncio.sleep(self.polling)
                result = await client.get(
                    f"{self.BASE_URL}/res.php",
                    params={
                        "key": self.api_key,
                        "action": "get",
                        "id": captcha_id,
                        "json": 1,
                    },
                )
                payload = result.json()
                if payload.get("status") == 1:
                    return payload["request"]
                if payload.get("request") == "CAPCHA_NOT_READY":
                    continue
                raise RuntimeError(f"Erro 2Captcha: {payload.get('request')}")

            raise TimeoutError("Timeout ao resolver hCaptcha.")
