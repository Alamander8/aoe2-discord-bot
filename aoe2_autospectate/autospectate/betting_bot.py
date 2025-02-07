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

        await asyncio.sleep(30)
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
        
        # Get modified cooldown if user has a unit type
        modified_cooldown = self.claim_cooldown_time
        if civ := self.civ_manager.get_user_civ(user_id):
            modified_cooldown = self.claim_cooldown_time * civ.pound_cooldown_multiplier
        
        # Check cooldown with modified time
        if user_id in self.claim_cooldowns:
            time_since_last = current_time - self.claim_cooldowns[user_id]
            if time_since_last < modified_cooldown:
                minutes_left = int((modified_cooldown - time_since_last) / 60)
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

        # Track round results
        self.last_round_results = []
        
        # Process winners
        winning_bets = [bet for bet in self.betting_pool.bets.values() 
                    if bet.team == winner and not bet.user_id.startswith('house_')]
        
        if winning_bets:
            await self.get_channel(self.channel).send(f"Results for {winner} victory:")
        
        for bet in winning_bets:
            share = bet.amount / winning_pool
            winnings = bet.amount + int(losing_pool * share)
            profit = winnings - bet.amount
            
            # Update points
            self.user_points[bet.user_id] = self.user_points.get(bet.user_id, 0) + winnings
            
            # Track result
            self.last_round_results.append({
                'username': bet.username,
                'profit': profit,
                'bet_amount': bet.amount
            })
            
            await self.get_channel(self.channel).send(
                f"@{bet.username} won {winnings:,} pounds! "
                f"(Bet: {bet.amount:,}, Bonus: +{int(losing_pool * share):,})"
            )
        
        # Track losers
        losing_bets = [bet for bet in self.betting_pool.bets.values() 
                    if bet.team != winner and not bet.user_id.startswith('house_')]
        
        for bet in losing_bets:
            self.last_round_results.append({
                'username': bet.username,
                'profit': -bet.amount,
                'bet_amount': bet.amount
            })

        # Save updated points
        self.save_points()
        self.betting_pool = None
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
        """Show available commands in Twitch-friendly format"""
        
        # Core betting commands (most used)
        await ctx.send("BETTING: !bet <amount> <blue/red> to place bet · !mybet to see your bet · !pool to see odds")
        
        # Stats and results
        await ctx.send("RESULTS: !winners to see biggest wins · !losers to see biggest losses · !leaderboard for top salt holders")
        
        # Salt management
        await ctx.send("SALT: !pound to get salt (30m cooldown) · !salt to check balance")
        
        # Unit system
        await ctx.send("UNITS: !units to see types · !unit <type> to pick · !profile to check your unit")

        
    @commands.command(name='pool')
    async def pool_command(self, ctx):
        """Show current betting pool information"""
        if not hasattr(self, 'betting_pool') or not self.betting_pool:
            await ctx.send("No active betting pool!")
            return
        
        total_pool = self.betting_pool.total_blue + self.betting_pool.total_red
        
        # Prevent division by zero
        blue_odds = (total_pool / self.betting_pool.total_blue) if self.betting_pool.total_blue > 0 else 0
        red_odds = (total_pool / self.betting_pool.total_red) if self.betting_pool.total_red > 0 else 0
        
        # Count unique betters per side (excluding house)
        blue_betters = sum(1 for bet in self.betting_pool.bets.values() 
                        if bet.team == 'Blue' and not bet.user_id.startswith('house_'))
        red_betters = sum(1 for bet in self.betting_pool.bets.values() 
                        if bet.team == 'Red' and not bet.user_id.startswith('house_'))
        
        await ctx.send(
            f"Current Pool: {total_pool:,} 🧂\n"
            f"Blue: {self.betting_pool.total_blue:,} (x{blue_odds:.2f}) [{blue_betters} betters]\n"
            f"Red: {self.betting_pool.total_red:,} (x{red_odds:.2f}) [{red_betters} betters]"
        )


    @commands.command(name='mybet')
    async def mybet_command(self, ctx):
        """Show user's current bet"""
        user_id = str(ctx.author.id)
        
        if not hasattr(self, 'betting_pool') or not self.betting_pool:
            await ctx.send("No active betting pool!")
            return
        
        user_bet = self.betting_pool.bets.get(user_id)
        if user_bet:
            # Calculate potential winnings
            total_pool = self.betting_pool.total_blue + self.betting_pool.total_red
            team_pool = (self.betting_pool.total_blue 
                        if user_bet.team == 'Blue' 
                        else self.betting_pool.total_red)
            
            potential_share = (user_bet.amount / team_pool) if team_pool > 0 else 0
            potential_winnings = user_bet.amount + int((total_pool - team_pool) * potential_share)
            
            await ctx.send(
                f"@{ctx.author.name} Your bet: {user_bet.amount:,} 🧂 on {user_bet.team}\n"
                f"Potential win: {potential_winnings:,} 🧂 "
                f"(+{potential_winnings - user_bet.amount:,})"
            )
        else:
            await ctx.send(f"@{ctx.author.name} You haven't placed a bet this round")

    @commands.command(name='leaderboard')
    async def leaderboard_command(self, ctx):
        """Show top 4 salt holders, excluding house accounts"""
        # Filter out house accounts and sort by value
        player_totals = {
            user_id: amount 
            for user_id, amount in self.user_points.items() 
            if not user_id.startswith('house_')
        }
        
        sorted_users = sorted(
            player_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )[:4]
        
        if not sorted_users:
            await ctx.send("No salt holders yet!")
            return
        
        entries = []
        medals = ["🥇", "🥈", "🥉", "🏅"]  # Medals for top 4
        
        for i, (user_id, amount) in enumerate(sorted_users):
            entries.append(f"{medals[i]} {amount:,} 🧂")
        
        await ctx.send("TOP SALT TOTALS:\n" + "\n".join(entries))




    @commands.command(name='winners')
    async def winners_command(self, ctx):
        """Show biggest winners from last betting round"""
        if not hasattr(self, 'last_round_results'):
            await ctx.send("No completed betting rounds yet!")
            return
        
        sorted_winners = sorted(
            self.last_round_results,
            key=lambda x: x['profit'],
            reverse=True
        )[:3]
        
        if not sorted_winners:
            await ctx.send("No winners from last round!")
            return
        
        entries = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, result in enumerate(sorted_winners):
            if result['profit'] > 0:  # Only show actual winners
                entries.append(
                    f"{medals[i]} {result['username']}: +{result['profit']:,} 🧂"
                )
        
        if entries:
            await ctx.send("BIGGEST WINNERS:\n" + "\n".join(entries))
        else:
            await ctx.send("No winners last round!")

    @commands.command(name='losers')
    async def losers_command(self, ctx):
        """Show biggest losers from last betting round"""
        if not hasattr(self, 'last_round_results'):
            await ctx.send("No completed betting rounds yet!")
            return
        
        sorted_losers = sorted(
            self.last_round_results,
            key=lambda x: x['profit']
        )[:3]  # Ascending order for biggest losses
        
        if not sorted_losers:
            await ctx.send("No results from last round!")
            return
        
        entries = []
        medals = ["💀", "☠️", "👻"]  # Funny emojis for losers
        
        for i, result in enumerate(sorted_losers):
            if result['profit'] < 0:  # Only show actual losers
                entries.append(
                    f"{medals[i]} {result['username']}: {result['profit']:,} 🧂"
                )
        
        if entries:
            await ctx.send("BIGGEST LOSSES:\n" + "\n".join(entries))
        else:
            await ctx.send("No losses last round!")





    @commands.command(name='units')
    async def civs_command(self, ctx):
        """Show available unit specializations"""
        basic_info = "⚔️ AVAILABLE UNITS (200 salt to pick) ⚔️"
        
        unit_list = (
            f"{self.civ_manager.CIVILIZATIONS['archer'].badge} Archer: +30% !pound rewards\n"
            f"{self.civ_manager.CIVILIZATIONS['infantry'].badge} Infantry: 40% faster !pound cooldown\n"
            f"{self.civ_manager.CIVILIZATIONS['cavalry'].badge} Cavalry: Double rewards, 50% longer cooldown\n"
            f"{self.civ_manager.CIVILIZATIONS['eagle'].badge} Eagle: 30% cheaper techs"
        )

        await ctx.send(basic_info)
        await ctx.send(unit_list)

    @commands.command(name='unit')
    async def civ_command(self, ctx, unit_type: str = None):
        """Select or view unit type"""
        user_id = str(ctx.author.id)
        
        # If no unit specified, show current unit
        if not unit_type:
            current_unit = self.civ_manager.get_user_civ(user_id)
            if current_unit:
                await ctx.send(f"@{ctx.author.name} You are specialized in {current_unit.name} {current_unit.badge}")
            else:
                await ctx.send(f"@{ctx.author.name} You haven't selected a unit type yet. Use !units to see options")
            return

        # Force lowercase for consistency with our stored values
        unit_type = unit_type.lower()

        # Check if user already has a unit type
        current_unit = self.civ_manager.get_user_civ(user_id)
        cost = 1000 if current_unit else 200  # Switch cost vs initial cost
        
        # Check if user has enough salt
        if self.user_points.get(user_id, 0) < cost:
            await ctx.send(f"@{ctx.author.name} You need {cost} salt to {'switch unit type' if current_unit else 'select a unit type'}")
            return

        # Try to select unit type
        success, message = self.civ_manager.select_civilization(user_id, unit_type)
        if success:
            # Deduct salt
            self.user_points[user_id] = self.user_points.get(user_id, 0) - cost
            await ctx.send(f"@{ctx.author.name} {message} (-{cost} salt)")
            self.save_points()
        else:
            await ctx.send(f"@{ctx.author.name} {message}")

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

    @commands.command(name='profile')
    async def myciv_command(self, ctx):
        """Show detailed information about your civilization"""
        user_id = str(ctx.author.id)
        civ = self.civ_manager.get_user_civ(user_id)
        
        if not civ:
            await ctx.send(f"@{ctx.author.name} You haven't selected a Unit type yet. Use !units to see options")
            return

        await ctx.send(
            f"@{ctx.author.name} UnitType: {civ.badge} {civ.name}\n"
            f"Bonus: {civ.description}"
        )