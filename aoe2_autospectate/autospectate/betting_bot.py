import asyncio
from twitchio.ext import commands
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import time
import logging
import random
import os
import shutil
from civ_manager import CivilizationManager

@dataclass
class Bet:
    user_id: str
    username: str
    amount: int
    team: str
    timestamp: float

@dataclass
class BettingPool:
    is_active: bool
    total_blue: int
    total_red: int
    bets: Dict[str, Bet]
    start_time: float
    end_time: Optional[float]

class BettingBot(commands.Bot):
    def __init__(self, token: str, channel: str):
        token = token.replace('oauth:', '')
        super().__init__(
            token=token,
            nick='saltyempires',
            prefix='!',
            initial_channels=[channel]
        )
        self.channel = channel
        self.claim_cooldowns = {}  # Track when users last claimed
        self.claim_cooldown_time = 1800  # 30 minutes in seconds
        self.points_file = 'user_points.json'
        self.user_points = self.load_points()
        self._tasks = set()
        self.civ_manager = CivilizationManager()
        self.betting_pool = None
        logging.info(f"BettingBot initialized for channel: {channel}")

    def load_points(self) -> Dict[str, int]:
        try:
            with open(self.points_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_points(self):
        """Save points with verification and backup"""
        try:
            # Create backup of current file if it exists
            if os.path.exists(self.points_file):
                backup_file = f"{self.points_file}.backup"
                shutil.copy2(self.points_file, backup_file)

            # Save new data
            with open(self.points_file, 'w') as f:
                json.dump(self.user_points, f)

            # Verify save
            with open(self.points_file, 'r') as f:
                saved_data = json.load(f)
                if saved_data != self.user_points:
                    logging.error("Point save verification failed!")
                    return False

            logging.info(f"Points saved successfully. Active users: {len(self.user_points)}")
            return True

        except Exception as e:
            logging.error(f"Error saving points: {e}")
            return False

    async def start_betting(self, duration: int = 180):
        # Don't create new pool if exists and active
        if hasattr(self, 'betting_pool') and self.betting_pool and self.betting_pool.is_active:
            return False

        if not hasattr(self, 'betting_pool') or not self.betting_pool:
            self.betting_pool = BettingPool(
                is_active=True,
                total_blue=0,
                total_red=0,
                bets={},
                start_time=time.time(),
                end_time=time.time() + duration
            )
        else:
            self.betting_pool.is_active = True
            self.betting_pool.start_time = time.time()
            self.betting_pool.end_time = time.time() + duration

        # Add house bets
        house_blue = random.randint(40, 200)
        house_red = random.randint(40, 200)
        
        self.betting_pool.bets['house_blue'] = Bet(
            user_id='house_blue',
            username='SaltCasino',
            amount=house_blue,
            team='Blue',
            timestamp=time.time()
        )
        self.betting_pool.bets['house_red'] = Bet(
            user_id='house_red',
            username='SaltCasino',
            amount=house_red,
            team='Red',
            timestamp=time.time()
        )
        
        self.betting_pool.total_blue += house_blue
        self.betting_pool.total_red += house_red

        await self.get_channel(self.channel).send(
            f"Betting is now open for {duration} seconds! House bets {house_blue} on Blue and {house_red} on Red. Use !bet <amount> blue/red"
        )
        

        # Schedule 30-second warning
        await asyncio.sleep(duration - 30)
        if self.betting_pool and self.betting_pool.is_active:
            total_pool = self.betting_pool.total_blue + self.betting_pool.total_red
            await self.get_channel(self.channel).send(
                f"⚠️ 30 SECONDS LEFT TO BET! Current pool: {total_pool} 🧂 (Blue: {self.betting_pool.total_blue}, Red: {self.betting_pool.total_red})"
            )



        await asyncio.sleep(duration)
        await self.close_betting()
        return True

    async def close_betting(self):
        if not self.betting_pool or not self.betting_pool.is_active:
            return False

        self.betting_pool.is_active = False
        self.betting_pool.end_time = time.time()

        total_pool = self.betting_pool.total_blue + self.betting_pool.total_red
        await self.get_channel(self.channel).send(
            f"Betting closed! Total pool: {total_pool} points "
            f"(Blue: {self.betting_pool.total_blue}, Red: {self.betting_pool.total_red})"
        )
        return True

    async def event_ready(self):
        logging.info(f"Bot ready | {self.nick}")
        channel = self.get_channel(self.channel)
        if channel:
            await channel.send("Salt Casino Online! Use !bet <amount> <blue/red> to place bets!")

    async def event_channel_joined(self, channel):
        logging.info(f"Joined channel: {channel.name}")
        await channel.send("Betting Starts when spectator scene switches, and is open for 3 minutes")

    async def event_message(self, message):
        if message.echo:
            return

        logging.info(f"Message received: {message.content} from {message.author.name}")
        try:
            await self.handle_commands(message)
        except Exception as e:
            logging.error(f"Error handling command: {e}")

    @commands.command(name='pound')
    async def claim_command(self, ctx):
        user_id = str(ctx.author.id)
        current_time = time.time()
        
        # Check cooldown
        if user_id in self.claim_cooldowns:
            time_since_last = current_time - self.claim_cooldowns[user_id]
            if time_since_last < self.claim_cooldown_time:
                minutes_left = int((self.claim_cooldown_time - time_since_last) / 60)
                await ctx.send(f"@{ctx.author.name} You can claim more salt in {minutes_left} minutes!")
                return

        # If user is new, give starting amount
        if user_id not in self.user_points:
            self.user_points[user_id] = 500
            await ctx.send(f"@{ctx.author.name} Welcome! You received 500 pounds of starting salt!")
        else:
            # Give random amount between 40 and 200
            claim_amount = random.randint(40, 200)
            if civ := self.civ_manager.get_user_civ(user_id):
                claim_amount = int(claim_amount * civ.pound_multiplier)
            self.user_points[user_id] += claim_amount
            display_name = self.civ_manager.get_display_name(ctx.author.name, user_id)
            await ctx.send(f"@{ctx.author.name} You claimed {claim_amount} pounds of salt! You now have {self.user_points[user_id]} total!")

        # Update cooldown and save
        self.claim_cooldowns[user_id] = current_time
        self.save_points()  # Save after every points change
    
    
    @commands.command(name='bet')
    async def bet_command(self, ctx, amount: str = None, team: str = None):
        logging.info(f"Bet command received - Amount: {amount}, Team: {team}, User: {ctx.author.name}")
        

        if amount is None or team is None:
            await ctx.send("Usage: !bet <amount> <blue/red>")
            return

        try:
            amount = int(amount)
            if amount < 10:  # Add minimum bet check here
                await ctx.send(f"@{ctx.author.name} Minimum bet is 10 pounds!")
                return
                
            if amount <= 0:
                raise ValueError
        except ValueError:
            await ctx.send("Please provide a valid positive number for your bet")
            return


        user_id = str(ctx.author.id)
        current_points = self.user_points.get(user_id, 0)
        if current_points < amount: #point check before bet processing
            await ctx.send(f"@{ctx.author.name} Not enough salt! You have {current_points}")
            return
        
        if not hasattr(self, 'betting_pool') or not self.betting_pool.is_active:
            await ctx.send("No active betting round!")
            return
            
        # Check if user already bet this round
        if user_id in self.betting_pool.bets:
            await ctx.send(f"@{ctx.author.name} You already placed a bet this round!")
            return

        if amount is None or team is None:
            await ctx.send("Usage: !bet <amount> <blue/red>")
            return

        team = team.capitalize()
        if team not in ['Blue', 'Red']:
            await ctx.send("Please bet on either 'blue' or 'red'")
            return

        try:
            amount = int(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await ctx.send("Please provide a valid positive number for your bet")
            return

        # current_points = self.user_points.get(user_id, 0)
        # if current_points < amount:
        #     await ctx.send(f"@{ctx.author.name} Not enough points! You have {current_points}")
        #     return

        self.betting_pool.bets[user_id] = Bet(
            user_id=user_id,
            username=ctx.author.name,
            amount=amount,
            team=team,
            timestamp=time.time()
        )

        if team == 'Blue':
            self.betting_pool.total_blue += amount
        else:
            self.betting_pool.total_red += amount

        self.user_points[user_id] = current_points - amount
        self.save_points()

        pool_total = getattr(self.betting_pool, f"total_{team.lower()}")
        await ctx.send(f"@{ctx.author.name} bet {amount} pounds of salt on {team}! Total {team} pool: {pool_total}")




    async def resolve_bets(self, winner: str):
        if not self.betting_pool or self.betting_pool.is_active:
            return False

        total_pool = self.betting_pool.total_blue + self.betting_pool.total_red
        winning_pool = self.betting_pool.total_blue if winner == 'Blue' else self.betting_pool.total_red
        losing_pool = total_pool - winning_pool

        if winning_pool == 0:
            return False

        # Group all winners first
        winning_bets = [bet for bet in self.betting_pool.bets.values() if bet.team == winner]
        
        # Send a single summary message first
        if winning_bets:
            await self.get_channel(self.channel).send(f"Results for {winner} victory:")
        
        # Process each winner
        for bet in winning_bets:
            share = bet.amount / winning_pool
            winnings = bet.amount + int(losing_pool * share)
            
            # Update points
            self.user_points[bet.user_id] = self.user_points.get(bet.user_id, 0) + winnings
            
            # Single announcement per winner
            await self.get_channel(self.channel).send(
                f"@{bet.username} won {winnings} pounds! (Bet: {bet.amount}, Bonus: {int(losing_pool * share)})"
            )

        # Save updated points
        self.save_points()
        self.betting_pool = None  # Clear betting pool after resolution
        return True


    @commands.command(name='salt')
    async def points_command(self, ctx):
        """Check your current points"""
        user_id = str(ctx.author.id)
        logging.info(f"Checking points for user {ctx.author.name} with ID {user_id}")
        logging.info(f"Current points data: {self.user_points}")
        
        current_points = self.user_points.get(user_id, 0)
        await ctx.send(f"@{ctx.author.name} you have {current_points} pounds of salt!")


    @commands.command(name='help')
    async def help_command(self, ctx):
        """Show available commands"""
        help_text = (
            "🎲 Available Commands 🎲\n"
            "!pound - Claim salt (30 min cooldown)\n"
            "!bet <amount> <blue/red> - Place a bet\n"
            "!salt - Check your salt balance\n"
            "!pool - View current betting pool\n"
            "!mybets - View your active bets\n"
            "!leaderboard - View top 5 salt holders\n"
            "\n🏰 Civilization Commands 🏰\n"
            "!civs - See available civilizations\n"
            "!civ <name> - Select a civilization (200 salt)\n"
            "!myciv - View your current civilization\n"
            "\n!help - Show this message"
        )
        await ctx.send(help_text)

    @commands.command(name='pool')
    async def pool_command(self, ctx):
        """Show current betting pool information"""
        if not hasattr(self, 'betting_pool') or not self.betting_pool or not self.betting_pool.is_active:
            await ctx.send("No active betting pool!")
            return
            
        total_pool = self.betting_pool.total_blue + self.betting_pool.total_red
        blue_odds = (total_pool / self.betting_pool.total_blue) if self.betting_pool.total_blue > 0 else 0
        red_odds = (total_pool / self.betting_pool.total_red) if self.betting_pool.total_red > 0 else 0
        
        await ctx.send(
            f"Current Pool: {total_pool} 🧂 | "
            f"Blue: {self.betting_pool.total_blue} (x{blue_odds:.2f}) | "
            f"Red: {self.betting_pool.total_red} (x{red_odds:.2f})"
        )

    @commands.command(name='mybets')
    async def mybets_command(self, ctx):
        """Show user's active bets"""
        user_id = str(ctx.author.id)
        if not hasattr(self, 'betting_pool') or not self.betting_pool:
            await ctx.send("No active betting pool!")
            return
            
        user_bet = self.betting_pool.bets.get(user_id)
        if user_bet:
            await ctx.send(
                f"@{ctx.author.name} has bet {user_bet.amount} 🧂 on {user_bet.team}"
            )
        else:
            await ctx.send(f"@{ctx.author.name} has no active bets")

    @commands.command(name='leaderboard')
    async def leaderboard_command(self, ctx):
        """Show top 5 salt holders"""
        sorted_users = sorted(
            self.user_points.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:5]
        
        leaderboard = "🏆 Salt Leaderboard 🏆\n"
        for i, (user_id, points) in enumerate(sorted_users, 1):
            username = await self._get_username(user_id)
            leaderboard += f"{i}. {username}: {points} 🧂\n"
        
        await ctx.send(leaderboard)


    @commands.command(name='civs')
    async def civs_command(self, ctx):
        """Show available civilizations"""
        await ctx.send(self.civ_manager.format_civ_list())

    @commands.command(name='civ')
    async def civ_command(self, ctx, civilization: str = None):
        """Select or view civilization"""
        user_id = str(ctx.author.id)
        
        # If no civ specified, show current civ
        if not civilization:
            current_civ = self.civ_manager.get_user_civ(user_id)
            if current_civ:
                await ctx.send(f"@{ctx.author.name} You are playing as {current_civ.name} {current_civ.badge}")
            else:
                await ctx.send(f"@{ctx.author.name} You haven't selected a civilization yet. Use !civs to see options")
            return

        # Check if user already has a civ
        current_civ = self.civ_manager.get_user_civ(user_id)
        cost = 1000 if current_civ else 200  # Switch cost vs initial cost
        
        # Check if user has enough salt
        if self.user_points.get(user_id, 0) < cost:
            await ctx.send(f"@{ctx.author.name} You need {cost} salt to {'switch civilizations' if current_civ else 'select a civilization'}")
            return

        # Try to select civilization
        success, message = self.civ_manager.select_civilization(user_id, civilization)
        if success:
            # Deduct salt
            self.user_points[user_id] = self.user_points.get(user_id, 0) - cost
            await ctx.send(f"@{ctx.author.name} {message} (-{cost} salt)")
            self.save_points()
        else:
            await ctx.send(f"@{ctx.author.name} {message}")

    @commands.command(name='myciv')
    async def myciv_command(self, ctx):
        """Show detailed information about your civilization"""
        user_id = str(ctx.author.id)
        civ = self.civ_manager.get_user_civ(user_id)
        
        if not civ:
            await ctx.send(f"@{ctx.author.name} You haven't selected a civilization yet. Use !civs to see options")
            return

        await ctx.send(
            f"@{ctx.author.name} Civilization: {civ.badge} {civ.name}\n"
            f"Bonus: {civ.description}"
        )