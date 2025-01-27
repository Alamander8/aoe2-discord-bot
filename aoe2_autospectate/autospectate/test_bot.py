# test_bot.py
from betting_bot import BettingBot
import asyncio

async def main():
    bot = BettingBot(token='your_oauth_token', channel='your_channel')
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())