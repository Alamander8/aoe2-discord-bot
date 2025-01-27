import asyncio
import logging
from betting_bot import BettingBot, Bet, BettingPool
import time

class MockContext:
    def __init__(self, bot, author_name, author_id):
        self.bot = bot
        self.author = type('MockAuthor', (), {'name': author_name, 'id': author_id})
        self.channel = bot.get_channel(bot.channel)
        self.message = type('MockMessage', (), {'content': ''})

    async def send(self, content):
        logging.info(f"Bot response: {content}")

async def simulate_betting_round():
    bot = BettingBot(token="oupa8z2646y8al78slb32indxg2lyw", channel="saltyempires")
    bot_task = asyncio.create_task(bot.start())
    await asyncio.sleep(2)
    
    try:
        test_users = ["test_user1", "test_user2", "alamandertv"]
        # Instead of setting points directly, only initialize if not present
        for user in test_users:
            if user not in bot.user_points:
                bot.user_points[user] = 1000
                logging.info(f"Initialized new user {user} with 1000 points")
            else:
                logging.info(f"Existing user {user} has {bot.user_points[user]} points")
        
        # Create betting pool
        bot.betting_pool = BettingPool(
            is_active=True,
            total_blue=0,
            total_red=0,
            bets={},
            start_time=time.time(),
            end_time=time.time() + 30
        )

        # Place test bets directly
        bet_data = [
            (bot.betting_pool.bets, "test_user1", "test_user1", 300, "Red"),
            (bot.betting_pool.bets, "test_user2", "test_user2", 400, "Red"),
            (bot.betting_pool.bets, "alamandertv", "alamandertv", 100, "Blue")
        ]

        for pool, user_id, username, amount, team in bet_data:
            pool[user_id] = Bet(
                user_id=user_id,
                username=username,
                amount=amount,
                team=team,
                timestamp=time.time()
            )
            if team == "Blue":
                bot.betting_pool.total_blue += amount
            else:
                bot.betting_pool.total_red += amount
            bot.user_points[user_id] -= amount

        logging.info("\nVerifying bet registration:")
        for user_id, bet in bot.betting_pool.bets.items():
            logging.info(f"{bet.username}: {bet.amount} on {bet.team}")
        
        await bot.resolve_bets("Blue")
        
        logging.info("\nFinal points:")
        for user in test_users:
            logging.info(f"{user}: {bot.user_points[user]} points")
            
    finally:
        await bot.close()
        bot_task.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(simulate_betting_round())