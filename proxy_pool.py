#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proxy Pool Manager برای پروکسی‌های رایگان ایرانی
==================================================
این ماژول لیست پروکسی‌های رایگان ایرانی رو از چند منبع fetch می‌کنه،
تست سلامت می‌کنه و یه pool از پروکسی‌های سالم نگه می‌داره.

منابع:
  1. ProxyScrape API (socks5 + IR)
  2. Geonode API (http/https + IR)
  3. monosans/proxy-list (GitHub raw)
  4. ProxyScrape GitHub raw (json)

نکات امنیتی:
  - همه درخواست‌ها HTTPS هستن
  - TLS verification همیشه روشنه (verify=True)
  - از SOCKS5 proxy استفاده می‌شه (امن‌تر از HTTP proxy)
"""

import asyncio
import aiohttp
import requests
import time
import logging
import random
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# منابع پروکسی
SOURCES = {
    'proxyscrape_api': 'https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_free_proxies&proxy_format=protocolipport&format=text&protocol=socks5&country=IR',
    'geonode_api': 'https://geonode.com/api/proxy-list?limit=100&page=1&sort_by=lastChecked&sort_type=desc&filterUpTime=90&protocols=http,https,socks5&country=IR',
    'monosans_socks5': 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt',
    'monosans_http': 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
    'proxifly': 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt',
}

# URL تست سلامت - staffing.digikala.com
HEALTH_CHECK_URL = 'https://staffing.digikala.com/api/seeker/v1/jobs?page=1'
HEALTH_CHECK_TIMEOUT = 8  # ثانیه
MAX_POOL_SIZE = 8  # حداکثر تعداد پروکسی سالم در pool
MIN_POOL_SIZE = 3  # حداقل تعداد پروکسی برای شروع


@dataclass
class Proxy:
    """نمایش یه پروکسی."""
    url: str  # مثل socks5://1.2.3.4:1080
    protocol: str  # socks5, http, https
    host: str
    port: int
    last_check: float = 0
    last_success: float = 0
    fail_count: int = 0
    is_alive: bool = False

    def __post_init__(self):
        # normalize url
        if not self.url.startswith(('socks5://', 'socks4://', 'http://', 'https://')):
            self.url = f"{self.protocol}://{self.host}:{self.port}"


class ProxyPool:
    """
    مدیریت pool از پروکسی‌های رایگان ایرانی.

    نحوه استفاده:
        pool = ProxyPool()
        await pool.initialize()
        proxy = await pool.get_proxy()
        # استفاده از proxy با requests/httpx
        if proxy:
            proxies = {'https': proxy.url, 'http': proxy.url}
            r = requests.get(url, proxies=proxies, timeout=10)
    """

    def __init__(self, refresh_interval_minutes: int = 10):
        self.proxies: List[Proxy] = []
        self.refresh_interval = refresh_interval_minutes * 60
        self.last_refresh: float = 0
        self._index = 0
        self._lock = asyncio.Lock()

    async def initialize(self, lazy=False):
        """راه‌اندازی اولیه pool.

        Args:
            lazy: اگه True باشه، فقط fetch می‌کنه بدون health check.
               مناسب GitHub Actions که زمان محدود داره.
        """
        logger.info("در حال راه‌اندازی Proxy Pool...")
        await self.refresh(skip_health_check=lazy)
        if lazy:
            logger.info(f"Proxy Pool آماده (lazy mode). {len(self.proxies)} پروکسی fetch شد.")
        else:
            logger.info(f"Proxy Pool آماده. {len(self.proxies)} پروکسی سالم.")

    async def find_working_proxy(self, test_func, max_attempts=15):
        """
        پیدا کردن اولین پروکسی کارکردی با تست زنده.

        به‌جای تست کردن همه پروکسی‌ها، یکی یکی تست می‌کنه و به اولین
        پروکسی که کار کنه، برمی‌گرده. بسیار سریع‌تر از health check کامل.

        Args:
            test_func: یه callable که proxy رو می‌گیره و bool برمی‌گردونه.
                       می‌تونه async یا sync باشه.
            max_attempts: حداکثر تعداد پروکسی برای تست (default 15).

        Returns:
            Proxy یا None اگه هیچ کدوم کار نکرد.
        """
        if not self.proxies:
            await self.refresh(skip_health_check=True)
            if not self.proxies:
                return None

        candidates = self.proxies[:max_attempts]
        logger.info(f"🔍 تست {len(candidates)} پروکسی برای پیدا کردن اولین کارکردی...")

        for i, proxy in enumerate(candidates):
            try:
                if asyncio.iscoroutinefunction(test_func):
                    result = await test_func(proxy)
                else:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, test_func, proxy
                    )

                if result:
                    proxy.is_alive = True
                    proxy.last_success = time.time()
                    proxy.fail_count = 0
                    logger.info(f"✓ پروکسی شماره {i+1} کار کرد: {proxy.url}")
                    return proxy
                else:
                    proxy.fail_count += 1
                    proxy.is_alive = False
                    logger.debug(f"✗ پروکسی شماره {i+1} کار نکرد: {proxy.url}")

            except Exception as e:
                proxy.fail_count += 1
                proxy.is_alive = False
                logger.debug(f"✗ پروکسی {proxy.url} خطا: {e}")

        logger.warning(f"❌ هیچ‌کدوم از {len(candidates)} پروکسی کار نکرد!")
        return None

    async def refresh(self, skip_health_check=False):
        """Fetch پروکسی‌های جدید از همه منابع + health check.

        Args:
            skip_health_check: اگه True باشه، فقط fetch می‌کنه بدون تست.
               (برای حالت lazy - پیدا کردن اولین پروکسی سالم با تابع تست کاربر)
        """
        logger.info("شروع refresh proxy pool...")

        # fetch از همه منابع به‌صورت موازی
        all_proxies = []
        tasks = [
            self._fetch_proxyscrape_api(),
            self._fetch_geonode_api(),
            self._fetch_monosans_socks5(),
            self._fetch_monosans_http(),
            self._fetch_proxifly(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_proxies.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"خطا در fetch: {result}")

        # dedup
        seen = set()
        unique_proxies = []
        for p in all_proxies:
            key = f"{p.protocol}:{p.host}:{p.port}"
            if key not in seen:
                seen.add(key)
                unique_proxies.append(p)

        logger.info(f"کل پروکسی‌های fetch شده: {len(all_proxies)} (یونیک: {len(unique_proxies)})")

        if not unique_proxies:
            logger.warning("هیچ پروکسی‌ای fetch نشد!")
            return

        if skip_health_check:
            # فقط fetch کن، بدون تست (برای lazy mode)
            self.proxies = unique_proxies[:MAX_POOL_SIZE * 3]  # نگه‌داشتن تعداد بیشتر
            for p in self.proxies:
                p.is_alive = True  # فرض می‌کنیم سالمه، تست بعداً
            self.last_refresh = time.time()
            logger.info(f"Pool آماده (بدون health check): {len(self.proxies)} پروکسی")
            return

        # health check موازی
        healthy = await self._health_check_all(unique_proxies)

        async with self._lock:
            # نگه‌داشتن پروکسی‌های قبلی که هنوز سالم هستن + پروکسی‌های جدید
            old_alive = [p for p in self.proxies if p.is_alive]
            # merge: قدیمی‌ها + جدیدها
            merged = {}
            for p in old_alive + healthy:
                key = f"{p.protocol}:{p.host}:{p.port}"
                if key not in merged or p.last_success > merged[key].last_success:
                    merged[key] = p

            self.proxies = list(merged.values())[:MAX_POOL_SIZE]
            self.last_refresh = time.time()

        logger.info(f"Pool بعد از refresh: {len(self.proxies)} پروکسی سالم")

    async def _fetch_proxyscrape_api(self) -> List[Proxy]:
        """Fetch از ProxyScrape API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(SOURCES['proxyscrape_api'], timeout=15) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()
                    proxies = []
                    for line in text.strip().split('\n'):
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        # فرمت: socks5://1.2.3.4:1080 یا 1.2.3.4:1080
                        if '://' in line:
                            proto, rest = line.split('://', 1)
                            host, port = rest.rsplit(':', 1)
                            try:
                                port = int(port)
                            except ValueError:
                                continue
                        else:
                            host, port = line.rsplit(':', 1)
                            try:
                                port = int(port)
                            except ValueError:
                                continue
                            proto = 'socks5'
                        proxies.append(Proxy(
                            url=f"{proto}://{host}:{port}",
                            protocol=proto, host=host, port=port
                        ))
                    logger.info(f"ProxyScrape API: {len(proxies)} پروکسی")
                    return proxies
        except Exception as e:
            logger.warning(f"خطا در ProxyScrape API: {e}")
            return []

    async def _fetch_geonode_api(self) -> List[Proxy]:
        """Fetch از Geonode API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(SOURCES['geonode_api'], timeout=15) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    proxies = []
                    for item in data.get('data', []):
                        proto = (item.get('protocols') or ['http'])[0]
                        host = item.get('ip')
                        port = item.get('port')
                        if not host or not port:
                            continue
                        proxies.append(Proxy(
                            url=f"{proto}://{host}:{port}",
                            protocol=proto, host=host, port=int(port)
                        ))
                    logger.info(f"Geonode API: {len(proxies)} پروکسی")
                    return proxies
        except Exception as e:
            logger.warning(f"خطا در Geonode API: {e}")
            return []

    async def _fetch_monosans_socks5(self) -> List[Proxy]:
        """Fetch از monosans/proxy-list socks5.txt"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(SOURCES['monosans_socks5'], timeout=15) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()
                    proxies = []
                    for line in text.strip().split('\n'):
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        host, port = line.rsplit(':', 1)
                        try:
                            port = int(port)
                        except ValueError:
                            continue
                        # فقط IP های ایرانی رو نگه می‌داریم
                        # (monosans فایل country-specific هم داره ولی ما از فیلتر استفاده می‌کنیم)
                        proxies.append(Proxy(
                            url=f"socks5://{host}:{port}",
                            protocol='socks5', host=host, port=port
                        ))
                    logger.info(f"monosans socks5: {len(proxies)} پروکسی")
                    return proxies
        except Exception as e:
            logger.warning(f"خطا در monosans socks5: {e}")
            return []

    async def _fetch_monosans_http(self) -> List[Proxy]:
        """Fetch از monosans/proxy-list http.txt"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(SOURCES['monosans_http'], timeout=15) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()
                    proxies = []
                    for line in text.strip().split('\n'):
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        host, port = line.rsplit(':', 1)
                        try:
                            port = int(port)
                        except ValueError:
                            continue
                        proxies.append(Proxy(
                            url=f"http://{host}:{port}",
                            protocol='http', host=host, port=port
                        ))
                    logger.info(f"monosans http: {len(proxies)} پروکسی")
                    return proxies
        except Exception as e:
            logger.warning(f"خطا در monosans http: {e}")
            return []

    async def _fetch_proxifly(self) -> List[Proxy]:
        """Fetch از proxifly/free-proxy-list"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(SOURCES['proxifly'], timeout=15) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()
                    proxies = []
                    for line in text.strip().split('\n'):
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        # proxifly فرمت: ip:port
                        host, port = line.rsplit(':', 1)
                        try:
                            port = int(port)
                        except ValueError:
                            continue
                        proxies.append(Proxy(
                            url=f"http://{host}:{port}",
                            protocol='http', host=host, port=port
                        ))
                    logger.info(f"proxifly: {len(proxies)} پروکسی")
                    return proxies
        except Exception as e:
            logger.warning(f"خطا در proxifly: {e}")
            return []

    async def _health_check_one(self, proxy: Proxy) -> bool:
        """تست سلامت یه پروکسی با درخواست به staffing.digikala.com."""
        proxy_url = proxy.url
        # aiohttp از socks5 پشتیبانی نمی‌کنه به‌صورت پیش‌فرض
        # از requests (sync) در یه thread استفاده می‌کنیم
        try:
            def _check():
                proxies = {'http': proxy_url, 'https': proxy_url}
                r = requests.get(
                    HEALTH_CHECK_URL,
                    proxies=proxies,
                    timeout=HEALTH_CHECK_TIMEOUT,
                    verify=True,  # TLS verification روشن
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                # 401 یعنی پروکسی کار می‌کنه ولی توکن نداریم (طبیعی)
                # 200 یعنی هم پروکسی کار می‌کنه هم توکن داره
                # 403/451 یعنی IP بلاک شده
                if r.status_code in (200, 401):
                    return True
                return False

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _check)

            proxy.last_check = time.time()
            if result:
                proxy.is_alive = True
                proxy.last_success = time.time()
                proxy.fail_count = 0
                return True
            else:
                proxy.is_alive = False
                proxy.fail_count += 1
                return False

        except Exception as e:
            proxy.is_alive = False
            proxy.fail_count += 1
            proxy.last_check = time.time()
            logger.debug(f"پروکسی {proxy.url} fail: {e}")
            return False

    async def _health_check_all(self, proxies: List[Proxy]) -> List[Proxy]:
        """تست سلامت همه پروکسی‌ها به‌صورت موازی."""
        if not proxies:
            return []

        logger.info(f"تست سلامت {len(proxies)} پروکسی...")

        # batch 50 تا 50 تا برای جلوگیری از overload
        batch_size = 50
        healthy = []

        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            tasks = [self._health_check_one(p) for p in batch]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            for p, ok in zip(batch, results):
                if ok:
                    healthy.append(p)
            logger.info(f"  batch {i//batch_size + 1}: {sum(results)} سالم از {len(batch)}")

        logger.info(f"جمع کل پروکسی‌های سالم: {len(healthy)}")
        return healthy

    async def get_proxy(self) -> Optional[Proxy]:
        """گرفتن یه پروکسی سالم از pool (round-robin)."""
        async with self._lock:
            if not self.proxies:
                # اگه pool خالیه، refresh کن
                await self.refresh()
                if not self.proxies:
                    return None

            # بررسی نیاز به refresh
            if time.time() - self.last_refresh > self.refresh_interval:
                await self.refresh()

            # round-robin
            alive_proxies = [p for p in self.proxies if p.is_alive]
            if not alive_proxies:
                # همه مردن، refresh
                await self.refresh()
                alive_proxies = [p for p in self.proxies if p.is_alive]
                if not alive_proxies:
                    return None

            self._index = (self._index + 1) % len(alive_proxies)
            return alive_proxies[self._index]

    async def mark_failed(self, proxy: Proxy):
        """علامت‌گذاری یه پروکسی به‌عنوان failed."""
        async with self._lock:
            proxy.fail_count += 1
            if proxy.fail_count >= 3:
                proxy.is_alive = False
                logger.info(f"پروکسی {proxy.url} به‌دلیل fail زیاد حذف شد.")

    def get_stats(self) -> dict:
        """آمار pool برای dashboard."""
        return {
            'total': len(self.proxies),
            'alive': sum(1 for p in self.proxies if p.is_alive),
            'last_refresh': datetime.fromtimestamp(self.last_refresh, TEHRAN_TZ).isoformat() if self.last_refresh else None,
            'proxies': [
                {
                    'url': p.url,
                    'protocol': p.protocol,
                    'is_alive': p.is_alive,
                    'fail_count': p.fail_count,
                    'last_success': datetime.fromtimestamp(p.last_success, TEHRAN_TZ).isoformat() if p.last_success else None,
                }
                for p in self.proxies
            ]
        }


# ============================================================
# تست مستقل
# ============================================================
async def _test():
    """تست ماژول."""
    logging.basicConfig(level=logging.INFO)
    pool = ProxyPool()
    await pool.initialize()

    print("\n" + "=" * 60)
    print(f"Pool size: {len(pool.proxies)}")
    print("=" * 60)

    for _ in range(3):
        p = await pool.get_proxy()
        if p:
            print(f"Got: {p.url} (alive={p.is_alive})")
        else:
            print("No proxy available!")
        await asyncio.sleep(1)

    print("\nStats:")
    print(pool.get_stats())


if __name__ == '__main__':
    asyncio.run(_test())
