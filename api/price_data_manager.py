"""
Price data management for on-demand downloads and coverage tracking.

This module provides:
- Coverage gap detection
- Priority-based download ordering
- Rate limit handling with retry logic
- Price data storage and retrieval
"""

import logging
import json
import os
import time
import requests
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional, Callable, Any
from datetime import datetime, timedelta
from collections import defaultdict

from api.database import get_db_connection

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when API rate limit is hit."""
    pass


class DownloadError(Exception):
    """Raised when download fails for non-rate-limit reasons."""
    pass


class PriceDataManager:
    """
    Manages price data availability, downloads, and coverage tracking.

    Responsibilities:
    - Check which dates/symbols have price data
    - Download missing data from Alpha Vantage
    - Track downloaded date ranges per symbol
    - Prioritize downloads to maximize date completion
    - Handle rate limiting gracefully
    """

    def __init__(
        self,
        db_path: str = "data/jobs.db",
        symbols_config: str = "configs/nasdaq100_symbols.json",
        api_key: Optional[str] = None
    ):
        """
        Initialize PriceDataManager.

        Args:
            db_path: Path to SQLite database
            symbols_config: Path to NASDAQ 100 symbols configuration
            api_key: Alpha Vantage API key (defaults to env var)
        """
        self.db_path = db_path
        self.symbols_config = symbols_config
        self.api_key = api_key or os.getenv("ALPHAADVANTAGE_API_KEY")

        # Load symbols list
        self.symbols = self._load_symbols()

        logger.info(f"Initialized PriceDataManager with {len(self.symbols)} symbols")

    def _load_symbols(self) -> List[str]:
        """Load NASDAQ 100 symbols from config file."""
        config_path = Path(self.symbols_config)

        if not config_path.exists():
            logger.warning(f"Symbols config not found: {config_path}. Using default list.")
            # Fallback to a minimal list
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

        with open(config_path, 'r') as f:
            config = json.load(f)

        return config.get("symbols", [])

    def get_available_dates(self) -> Set[str]:
        """
        Get all dates that have price data in database.

        Returns:
            Set of dates (YYYY-MM-DD) with data
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT date FROM price_data ORDER BY date")
        dates = {row[0] for row in cursor.fetchall()}

        conn.close()

        return dates

    def get_symbol_dates(self, symbol: str) -> Set[str]:
        """
        Get all dates that have data for a specific symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Set of dates with data for this symbol
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT date FROM price_data WHERE symbol = ? ORDER BY date",
            (symbol,)
        )
        dates = {row[0] for row in cursor.fetchall()}

        conn.close()

        return dates

    def get_missing_coverage(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Set[str]]:
        """
        Identify which symbols are missing data for which dates in range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict mapping symbol to set of missing dates
            Example: {"AAPL": {"2025-01-20", "2025-01-21"}, "MSFT": set()}
        """
        # Generate all dates in range
        requested_dates = self._expand_date_range(start_date, end_date)

        missing = {}

        for symbol in self.symbols:
            symbol_dates = self.get_symbol_dates(symbol)
            missing_dates = requested_dates - symbol_dates

            if missing_dates:
                missing[symbol] = missing_dates

        return missing

    def _expand_date_range(self, start_date: str, end_date: str) -> Set[str]:
        """
        Expand date range into set of all dates.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Set of all dates in range (inclusive)
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        dates = set()
        current = start

        while current <= end:
            dates.add(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        return dates

    def prioritize_downloads(
        self,
        missing_coverage: Dict[str, Set[str]],
        requested_dates: Set[str]
    ) -> List[str]:
        """
        Prioritize symbol downloads to maximize date completion.

        Strategy: Download symbols that complete the most requested dates first.

        Args:
            missing_coverage: Dict of symbol -> missing dates
            requested_dates: Set of dates we want to simulate

        Returns:
            List of symbols in priority order (highest impact first)
        """
        # Calculate impact score for each symbol
        impacts = []

        for symbol, missing_dates in missing_coverage.items():
            # Impact = number of requested dates this symbol would complete
            impact = len(missing_dates & requested_dates)

            if impact > 0:
                impacts.append((symbol, impact))

        # Sort by impact (descending)
        impacts.sort(key=lambda x: x[1], reverse=True)

        # Return symbols in priority order
        prioritized = [symbol for symbol, _ in impacts]

        logger.info(f"Prioritized {len(prioritized)} symbols for download")
        if prioritized:
            logger.debug(f"Top 5 symbols: {prioritized[:5]}")

        return prioritized

    def download_missing_data_prioritized(
        self,
        missing_coverage: Dict[str, Set[str]],
        requested_dates: Set[str],
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Download data in priority order until rate limited.

        Args:
            missing_coverage: Dict of symbol -> missing dates
            requested_dates: Set of dates being requested
            progress_callback: Optional callback for progress updates

        Returns:
            {
                "success": True/False,
                "downloaded": ["AAPL", "MSFT", ...],
                "failed": ["GOOGL", ...],
                "rate_limited": True/False,
                "dates_completed": ["2025-01-20", ...],
                "partial_dates": {"2025-01-21": 75}
            }
        """
        if not self.api_key:
            raise ValueError("ALPHAADVANTAGE_API_KEY not configured")

        # Prioritize downloads
        prioritized_symbols = self.prioritize_downloads(missing_coverage, requested_dates)

        if not prioritized_symbols:
            logger.info("No downloads needed - all data available")
            return {
                "success": True,
                "downloaded": [],
                "failed": [],
                "rate_limited": False,
                "dates_completed": sorted(requested_dates),
                "partial_dates": {}
            }

        logger.info(f"Starting priority download of {len(prioritized_symbols)} symbols")

        downloaded = []
        failed = []
        rate_limited = False

        # Download in priority order
        for i, symbol in enumerate(prioritized_symbols):
            try:
                # Progress callback
                if progress_callback:
                    progress_callback({
                        "current": i + 1,
                        "total": len(prioritized_symbols),
                        "symbol": symbol,
                        "phase": "downloading"
                    })

                # Download symbol data
                logger.info(f"Downloading {symbol} ({i+1}/{len(prioritized_symbols)})")
                data = self._download_symbol(symbol)

                # Store in database
                stored_dates = self._store_symbol_data(symbol, data, requested_dates)

                # Update coverage tracking
                if stored_dates:
                    self._update_coverage(symbol, min(stored_dates), max(stored_dates))

                downloaded.append(symbol)
                logger.info(f"✓ Downloaded {symbol} - {len(stored_dates)} dates stored")

            except RateLimitError as e:
                # Hit rate limit - stop downloading
                logger.warning(f"Rate limit hit after {len(downloaded)} downloads: {e}")
                rate_limited = True
                failed = prioritized_symbols[i:]  # Rest are undownloaded
                break

            except Exception as e:
                # Other error - log and continue
                logger.error(f"Failed to download {symbol}: {e}")
                failed.append(symbol)
                continue

        # Analyze coverage
        coverage_analysis = self._analyze_coverage(requested_dates)

        result = {
            "success": len(downloaded) > 0 or len(requested_dates) == len(coverage_analysis["completed_dates"]),
            "downloaded": downloaded,
            "failed": failed,
            "rate_limited": rate_limited,
            "dates_completed": coverage_analysis["completed_dates"],
            "partial_dates": coverage_analysis["partial_dates"]
        }

        logger.info(
            f"Download complete: {len(downloaded)} symbols downloaded, "
            f"{len(failed)} failed/skipped, rate_limited={rate_limited}"
        )

        return result

    def _download_symbol(self, symbol: str, retries: int = 3) -> Dict:
        """
        Download full price history for a symbol.

        Args:
            symbol: Stock symbol
            retries: Number of retry attempts for transient errors

        Returns:
            JSON response from Alpha Vantage

        Raises:
            RateLimitError: If rate limit is hit
            DownloadError: If download fails after retries
        """
        if not self.api_key:
            raise DownloadError("API key not configured")
        for attempt in range(retries):
            try:
                response = requests.get(
                    "https://www.alphavantage.co/query",
                    params={
                        "function": "TIME_SERIES_DAILY",
                        "symbol": symbol,
                        "outputsize": "full",  # Get full history
                        "apikey": self.api_key
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()

                    # Check for API error messages
                    if "Error Message" in data:
                        raise DownloadError(f"API error: {data['Error Message']}")

                    # Check for rate limit in response body
                    if "Note" in data:
                        note = data["Note"]
                        if "call frequency" in note.lower() or "rate limit" in note.lower():
                            raise RateLimitError(note)
                        # Other notes are warnings, continue
                        logger.warning(f"{symbol}: {note}")

                    if "Information" in data:
                        info = data["Information"]
                        if "premium" in info.lower() or "limit" in info.lower():
                            raise RateLimitError(info)

                    # Validate response has time series data
                    if "Time Series (Daily)" not in data or "Meta Data" not in data:
                        raise DownloadError(f"Invalid response format for {symbol}")

                    return data

                elif response.status_code == 429:
                    raise RateLimitError("HTTP 429: Too Many Requests")

                elif response.status_code >= 500:
                    # Server error - retry with backoff
                    if attempt < retries - 1:
                        wait_time = (2 ** attempt)
                        logger.warning(f"Server error {response.status_code}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    raise DownloadError(f"Server error: {response.status_code}")

                else:
                    raise DownloadError(f"HTTP {response.status_code}: {response.text[:200]}")

            except RateLimitError:
                raise  # Don't retry rate limits
            except DownloadError:
                raise  # Don't retry download errors
            except requests.RequestException as e:
                if attempt < retries - 1:
                    logger.warning(f"Request failed: {e}. Retrying...")
                    time.sleep(2)
                    continue
                raise DownloadError(f"Request failed after {retries} attempts: {e}")

        raise DownloadError(f"Failed to download {symbol} after {retries} attempts")

    def _store_symbol_data(
        self,
        symbol: str,
        data: Dict,
        requested_dates: Set[str]
    ) -> List[str]:
        """
        Store downloaded price data in database.

        Args:
            symbol: Stock symbol
            data: Alpha Vantage API response
            requested_dates: Only store dates in this set

        Returns:
            List of dates actually stored
        """
        time_series = data.get("Time Series (Daily)", {})

        if not time_series:
            logger.warning(f"No time series data for {symbol}")
            return []

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        stored_dates = []
        created_at = datetime.utcnow().isoformat() + "Z"

        for date, ohlcv in time_series.items():
            # Only store requested dates
            if date not in requested_dates:
                continue

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO price_data
                    (symbol, date, open, high, low, close, volume, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol,
                    date,
                    float(ohlcv.get("1. open", 0)),
                    float(ohlcv.get("2. high", 0)),
                    float(ohlcv.get("3. low", 0)),
                    float(ohlcv.get("4. close", 0)),
                    int(ohlcv.get("5. volume", 0)),
                    created_at
                ))
                stored_dates.append(date)
            except Exception as e:
                logger.error(f"Failed to store {symbol} {date}: {e}")
                continue

        conn.commit()
        conn.close()

        return stored_dates

    def _update_coverage(self, symbol: str, start_date: str, end_date: str) -> None:
        """
        Update coverage tracking for a symbol.

        Args:
            symbol: Stock symbol
            start_date: Start of date range downloaded
            end_date: End of date range downloaded
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        downloaded_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT OR REPLACE INTO price_data_coverage
            (symbol, start_date, end_date, downloaded_at, source)
            VALUES (?, ?, ?, ?, 'alpha_vantage')
        """, (symbol, start_date, end_date, downloaded_at))

        conn.commit()
        conn.close()

    def _analyze_coverage(self, requested_dates: Set[str]) -> Dict[str, Any]:
        """
        Analyze which requested dates have complete/partial coverage.

        Args:
            requested_dates: Set of dates requested

        Returns:
            {
                "completed_dates": ["2025-01-20", ...],  # All symbols available
                "partial_dates": {"2025-01-21": 75, ...}  # Date -> symbol count
            }
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        total_symbols = len(self.symbols)
        completed_dates = []
        partial_dates = {}

        for date in sorted(requested_dates):
            # Count symbols available for this date
            cursor.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_data WHERE date = ?",
                (date,)
            )
            count = cursor.fetchone()[0]

            if count == total_symbols:
                completed_dates.append(date)
            elif count > 0:
                partial_dates[date] = count

        conn.close()

        return {
            "completed_dates": completed_dates,
            "partial_dates": partial_dates
        }

    def get_available_trading_dates(
        self,
        start_date: str,
        end_date: str
    ) -> List[str]:
        """
        Get trading dates with complete data in range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Sorted list of dates with complete data (all symbols)
        """
        requested_dates = self._expand_date_range(start_date, end_date)
        analysis = self._analyze_coverage(requested_dates)

        return sorted(analysis["completed_dates"])
