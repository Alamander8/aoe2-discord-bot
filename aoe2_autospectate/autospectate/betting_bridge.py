import asyncio
import threading
from queue import Queue
import logging
from twitch_auth import get_app_access_token
from betting_bot import BettingBot
import requests

class BettingBridge:
    def __init__(self, channel: str):
        logging.info("Initializing BettingBridge...")
        self.channel = channel.lower()
        self.token = "oupa8z2646y8al78slb32indxg2lyw"
        
        # Test token validity
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Client-Id': 'gp762nuuoqcoxypju8c569th9wz7q5'
        }
        try:
            response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers)
            if response.status_code == 200:
                logging.info(f"Token validated: {response.json()}")
            else:
                logging.error(f"Token validation failed: {response.text}")
                raise Exception("Token validation failed")
        except Exception as e:
            logging.error(f"Token validation error: {e}")
            raise

        self.bot = None
        self.event_queue = Queue()
        self.bot_thread = None
        self.running = False
        self.loop = None

    def _run_bot(self):
        """Run bot in separate thread with proper event loop handling"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            self.bot = BettingBot(token=self.token, channel=self.channel)
            
            # Run the bot
            self.loop.run_until_complete(self.bot.start())
            
        except Exception as e:
            logging.error(f"Bot thread error: {e}", exc_info=True)
        finally:
            if self.loop and not self.loop.is_closed():
                self.loop.close()

    def start(self):
        """Start bot with proper thread management"""
        if self.running:
            return
            
        self.running = True
        self.bot_thread = threading.Thread(target=self._run_bot)
        self.bot_thread.daemon = True
        self.bot_thread.start()
        logging.info("Betting bridge started")

    def on_game_start(self):
        if not self.bot or not self.loop:
            logging.error("Bot not initialized")
            return
            
        asyncio.run_coroutine_threadsafe(
            self.bot.start_betting(duration=180),
            self.loop
        )
        logging.info("Started betting round")

    def on_game_end(self, winner: str):
        if not self.bot or not self.loop:
            logging.error("Bot not initialized")
            return
            
        asyncio.run_coroutine_threadsafe(
            self.bot.resolve_bets(winner),
            self.loop
        )
        logging.info(f"Resolved bets with winner: {winner}")
    def __init__(self, channel: str):
        logging.info("Initializing BettingBridge...")
        self.channel = channel.lower()  # Convert to lowercase
        self.token = "oupa8z2646y8al78slb32indxg2lyw"
        
        # Test token validity
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Client-Id': 'gp762nuuoqcoxypju8c569th9wz7q5'  # Client ID from token generator
        }
        try:
            response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers)
            logging.info(f"Token validation status: {response.status_code}")
            if response.status_code == 200:
                logging.info("Token validated successfully")
                logging.info(f"Response: {response.json()}")
            else:
                logging.error(f"Token validation failed: {response.text}")
        except Exception as e:
            logging.error(f"Token validation error: {e}")

        # Initialize rest of bridge
        self.bot = None
        self.event_queue = Queue()
        self.bot_thread = None
        self.running = False
        self.loop = None
        

    def start(self):
        """Start the bot in a separate thread"""
        logging.info("Starting betting bridge...")
        self.running = True
        self.bot_thread = threading.Thread(target=self._run_bot, name="BettingBotThread")
        self.bot_thread.daemon = True  # Make thread daemon so it doesn't block program exit
        self.bot_thread.start()

    def _run_bot(self):
        """Run the bot in a separate thread"""
        try:
            logging.info("Setting up event loop...")
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            logging.info(f"Creating bot instance for channel: {self.channel}")
            self.bot = BettingBot(
                token=f"oauth:{self.token}",  # Add oauth: prefix
                channel=self.channel
            )
            
            logging.info("Starting bot...")
            try:
                future = asyncio.ensure_future(self.bot.start(), loop=self.loop)
                self.loop.run_until_complete(future)
            except Exception as e:
                logging.error(f"Bot start error: {e}", exc_info=True)
                
        except Exception as e:
            logging.error(f"Error in _run_bot: {e}", exc_info=True)
        finally:
            try:
                if not self.loop.is_closed():
                    logging.info("Closing event loop...")
                    self.loop.close()
                logging.info("Bot shutdown complete")
            except Exception as e:
                logging.error(f"Error during cleanup: {e}", exc_info=True)


    def on_game_start(self):
        """Called when a new game starts"""
        logging.info("Betting Bridge: Starting new betting round")
        if self.bot:
            asyncio.run_coroutine_threadsafe(
                self.bot.start_betting(duration=180), 
                self.loop
            )

    def on_game_end(self, winner: str):
        """Called when a game ends"""
        logging.info(f"Betting Bridge: Ending betting round with winner: {winner}")
        if self.bot:
            asyncio.run_coroutine_threadsafe(
                self.bot.resolve_bets(winner), 
                self.loop
            )


    def stop(self):
        """Safely stop the bot"""
        if self.bot and self.loop and self.loop.is_running():
            async def cleanup():
                await self.bot.close()
            
            future = asyncio.run_coroutine_threadsafe(cleanup(), self.loop)
            future.result()
        
        self.running = False
        if self.bot_thread:
            self.bot_thread.join()