import logging
from typing import Optional

import asyncmy
from asyncmy.cursors import logger as asyncmy_logger

asyncmy_logger.setLevel("ERROR")  # I INSERT IGNORE, so I don't care about duplicate key warnings
logger = logging.getLogger()


async def execute_query(pool: asyncmy.Pool, query: str, params: iter = None,
                        many: bool = False, fetch: bool = False) -> Optional[list]:
    logger.info(f"Executing query: {query} (many={many}, fetch={fetch})")
    logger.debug(f"Params: {params}")
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            if many:
                await cursor.executemany(query, params)
            else:
                await cursor.execute(query, params)
            if fetch:
                return await cursor.fetchall()
