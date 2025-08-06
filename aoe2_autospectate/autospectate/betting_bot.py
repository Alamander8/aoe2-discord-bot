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


@dataclass
class Player:
    user_id: str
    username: str
    points: int = 500  # Default starting amount
    age: str = "Dark"
    biggest_win: int = 0
    biggest_loss: int = 0
    biggest_bet: int = 0
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    last_updated: float = time.time()  # Timestamp


class HouseBetting:
    """Manages house betting behavior"""
    
    # Base ranges for normal bets
    NORMAL_MIN = 80
    NORMAL_MAX = 250
    
    # Spicy bet ranges (when house decides to go big)
    SPICY_MIN = 350
    SPICY_MAX = 700
    
    # Chances for spicy bets
    SPICY_CHANCE = 0.10  # 10% chance for a spicy bet
    
    @staticmethod
    def get_bet_amount() -> int:
        """Get a single house bet amount with spicy chance"""
        if random.random() < HouseBetting.SPICY_CHANCE:
            return random.randint(HouseBetting.SPICY_MIN, HouseBetting.SPICY_MAX)
        return random.randint(HouseBetting.NORMAL_MIN, HouseBetting.NORMAL_MAX)
        
    @staticmethod
    def get_announcement(blue_amount: int, red_amount: int) -> str:
        """Get appropriate announcement based on bet sizes"""
        blue_spicy = blue_amount > HouseBetting.NORMAL_MAX
        red_spicy = red_amount > HouseBetting.NORMAL_MAX
        
        if blue_spicy and red_spicy:
            return f"House going BIG with {blue_amount} on Blue AND {red_amount} on Red!"
        elif blue_spicy:
            return f"House going BIG with {blue_amount} on Blue and {red_amount} on Red!"
        elif red_spicy:
            return f"House bets {blue_amount} on Blue and going BIG with {red_amount} on Red!"
        else:
            return f"House bets {blue_amount} on Blue and {red_amount} on Red."









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

    def load_points(self) -> Dict[str, Player]:
        try:
            with open(self.points_file, 'r') as f:
                data = json.load(f)
                
                # Create players dict
                players = {}
                for user_id, value in data.items():
                    if isinstance(value, dict):
                        # New format
                        players[user_id] = Player(
                            user_id=user_id,
                            username=value.get('username', 'Unknown'),
                            points=value.get('points', 500),
                            age=value.get('age', 'Dark'),  # Add this line to load the age
                            biggest_win=value.get('biggest_win', 0),
                            biggest_loss=value.get('biggest_loss', 0),
                            biggest_bet=value.get('biggest_bet', 0),
                            total_bets=value.get('total_bets', 0),
                            wins=value.get('wins', 0),
                            losses=value.get('losses', 0),
                            last_updated=value.get('last_updated', 0)
                        )
                    else:
                        # Old format - convert to new format
                        players[user_id] = Player(
                            user_id=user_id,
                            username='Unknown',
                            points=value
                        )
                return players
        except FileNotFoundError:
            return {}

    def save_points(self):
        """Save points with verification and backup"""
        try:
            # Create backup of current file if it exists
            if os.path.exists(self.points_file):
                backup_file = f"{self.points_file}.backup"
                shutil.copy2(self.points_file, backup_file)

            # Convert Player objects to dictionaries
            data_to_save = {}
            for user_id, player in self.user_points.items():
                if isinstance(player, Player):
                    data_to_save[user_id] = asdict(player)
                else:
                    # Handle old data format for compatibility
                    data_to_save[user_id] = player
            
            # Save new data
            with open(self.points_file, 'w') as f:
                json.dump(data_to_save, f, indent=2)

            # Verify save
            with open(self.points_file, 'r') as f:
                saved_data = json.load(f)
                # Basic verification
                if len(saved_data) != len(self.user_points):
                    logging.error("Point save verification failed!")
                    return False

            logging.info(f"Points saved successfully. Active users: {len(self.user_points)}")
            return True

        except Exception as e:
            logging.error(f"Error saving points: {e}")
            return False

    def get_player_points(self, user_id):
        """Get player points with compatibility for both formats"""
        if user_id not in self.user_points:
            return 0
        
        player = self.user_points[user_id]
        if isinstance(player, Player):
            return player.points
        return player  # Old format

    def update_player_points(self, user_id, username, amount):
        """Update player points with tracking"""
        if user_id not in self.user_points:
            self.user_points[user_id] = Player(user_id=user_id, username=username, points=amount)
        else:
            player = self.user_points[user_id]
            if isinstance(player, Player):
                player.points = max(0, player.points + amount)
                player.username = username  # Always update username
                player.last_updated = time.time()
            else:
                # Convert to new format
                new_points = max(0, player + amount)
                self.user_points[user_id] = Player(
                    user_id=user_id,
                    username=username,
                    points=new_points
                )


    def track_bet(self, user_id, username, amount, team):
        """Track bet statistics"""
        if user_id not in self.user_points:
            return
            
        player = self.user_points[user_id]
        if isinstance(player, Player):
            player.username = username
            player.total_bets += 1
            player.biggest_bet = max(player.biggest_bet, amount)
            player.last_updated = time.time()

    def track_win(self, user_id, win_amount):
        """Track win statistics"""
        if user_id not in self.user_points:
            return
            
        player = self.user_points[user_id]
        if isinstance(player, Player):
            player.wins += 1
            player.biggest_win = max(player.biggest_win, win_amount)
            player.last_updated = time.time()

    def track_loss(self, user_id, loss_amount):
        """Track loss statistics"""
        if user_id not in self.user_points:
            return
            
        player = self.user_points[user_id]
        if isinstance(player, Player):
            player.losses += 1
            player.biggest_loss = max(player.biggest_loss, loss_amount)
            player.last_updated = time.time()

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
        house_blue = HouseBetting.get_bet_amount()
        house_red = HouseBetting.get_bet_amount()
        
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

        announcement = HouseBetting.get_announcement(house_blue, house_red)
        await self.get_channel(self.channel).send(
            f"Betting is now open for {duration} seconds! {announcement} Use !bet <amount> blue/red"
        )
        

        # Schedule 30-second warning
        await asyncio.sleep(duration - 30)
        if self.betting_pool and self.betting_pool.is_active:
            total_pool = self.betting_pool.total_blue + self.betting_pool.total_red
            await self.get_channel(self.channel).send(
                f"⚠️ 30 SECONDS LEFT TO BET! Current pool: {total_pool} 🧂 (Blue: {self.betting_pool.total_blue}, Red: {self.betting_pool.total_red})"
            )

        await asyncio.sleep(55)
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

    @commands.command(name='ages')
    async def ages_command(self, ctx):
        """Display age advancement information"""
        await ctx.send("🏰 AGE ADVANCEMENT 🏰")
        await ctx.send("Dark Age → Feudal Age (1000 salt): Better pound (50-240) and faster cooldown (27 min)")
        await ctx.send("Feudal Age → Castle Age (2000 salt): Better pound (60-280) and faster cooldown (24 min)")
        await ctx.send("Castle Age → Imperial Age (5000 salt): Best pound (80-350) and fastest cooldown (20 min)")

    @commands.command(name='pound')
    async def claim_command(self, ctx):
        user_id = str(ctx.author.id)
        current_time = time.time()
        
        # Age benefits
        age_benefits = {
            "Dark": {"min": 40, "max": 200, "cooldown": 1800},
            "Feudal": {"min": 50, "max": 240, "cooldown": 1620},
            "Castle": {"min": 60, "max": 280, "cooldown": 1440},
            "Imperial": {"min": 80, "max": 350, "cooldown": 1200}
        }
        
        # Get player's age or default to Dark
        player = self.user_points.get(user_id, None)
        player_age = getattr(player, 'age', "Dark") if player else "Dark"
        
        # Get modified cooldown based on age
        modified_cooldown = age_benefits[player_age]["cooldown"]
        
        # Check cooldown with modified time
        if user_id in self.claim_cooldowns:
            time_since_last = current_time - self.claim_cooldowns[user_id]
            if time_since_last < modified_cooldown:
                minutes_left = int((modified_cooldown - time_since_last) / 60)
                await ctx.send(f"@{ctx.author.name} You can claim more salt in {minutes_left} minutes!")
                return

        # If user is new, give starting amount
        if user_id not in self.user_points:
            self.user_points[user_id] = Player(
                user_id=user_id,
                username=ctx.author.name,
                points=500,
                age="Dark"
            )
            await ctx.send(f"@{ctx.author.name} Welcome! You received 500 pounds of starting salt!")
        else:
            # Give random amount based on age
            min_amount = age_benefits[player_age]["min"]
            max_amount = age_benefits[player_age]["max"]
            claim_amount = random.randint(min_amount, max_amount)
            
            player.points += claim_amount
            await ctx.send(f"@{ctx.author.name} You claimed {claim_amount} pounds of salt! You now have {player.points} total!")

        # Update cooldown and save
        self.claim_cooldowns[user_id] = current_time
        self.save_points()


    @commands.command(name='advance')
    async def advance_command(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in self.user_points:
            await ctx.send(f"@{ctx.author.name} You need to claim some salt first!")
            return
            
        player = self.user_points[user_id]
        current_age = getattr(player, 'age', "Dark")
        
        # Age advancement costs and next age
        advancements = {
            "Dark": {"next": "Feudal", "cost": 1000},
            "Feudal": {"next": "Castle", "cost": 2000},
            "Castle": {"next": "Imperial", "cost": 5000},
            "Imperial": {"next": None, "cost": 0}
        }
        
        # Check if already at max age
        if current_age == "Imperial":
            await ctx.send(f"@{ctx.author.name} You've already reached the Imperial Age!")
            return
        
        # Get advancement details
        next_age = advancements[current_age]["next"]
        cost = advancements[current_age]["cost"]
        
        # Check if player has enough points
        if player.points < cost:
            await ctx.send(f"@{ctx.author.name} You need {cost} salt to advance to {next_age} Age. You have {player.points}.")
            return
        
        # Process advancement
        player.points -= cost
        player.age = next_age
        self.save_points()
        
        await ctx.send(f"🎉 @{ctx.author.name} has advanced to the {next_age} Age! 🎉")



    @commands.command(name='bet')
    async def bet_command(self, ctx, arg1: str = None, arg2: str = None):
        """More flexible bet command that handles different parameter orders and formatting"""
        logging.info(f"Bet command received - Args: {arg1} {arg2}, User: {ctx.author.name}")
        
        if arg1 is None or arg2 is None:
            await ctx.send("Usage: !bet <amount> <blue/red>")
            return
        
        # Determine which parameter is amount and which is team
        amount_str = None
        team = None
        
        # Try arg1 as amount, arg2 as team
        try:
            int(arg1)
            amount_str = arg1
            team = arg2.lower()
        except ValueError:
            # Try arg2 as amount, arg1 as team
            try:
                int(arg2)
                amount_str = arg2
                team = arg1.lower()
            except ValueError:
                await ctx.send("Please provide a valid bet amount and team (blue/red)")
                return
        
        # Standardize team name (accept variations)
        if team in ['blue', 'b', 'bl']:
            team = 'Blue'
        elif team in ['red', 'r', 're']:
            team = 'Red'
        else:
            await ctx.send("Please bet on either 'blue' or 'red'")
            return
        
        # Process amount
        try:
            amount = int(amount_str)
            if amount < 10:
                await ctx.send(f"@{ctx.author.name} Minimum bet is 10 pounds!")
                return
            if amount <= 0:
                raise ValueError
        except ValueError:
            await ctx.send("Please provide a valid positive number for your bet")
            return

        user_id = str(ctx.author.id)
        
        # Get current points with compatibility for both formats
        current_points = 0
        if user_id in self.user_points:
            player = self.user_points[user_id]
            if isinstance(player, Player):
                current_points = player.points
            else:
                current_points = player
        
        if current_points < amount:
            await ctx.send(f"@{ctx.author.name} Not enough salt! You have {current_points}")
            return
        
        if not hasattr(self, 'betting_pool') or not self.betting_pool.is_active:
            await ctx.send("No active betting round!")
            return
            
        # Check if user already bet this round
        if user_id in self.betting_pool.bets:
            await ctx.send(f"@{ctx.author.name} You already placed a bet this round!")
            return

        team = team.capitalize()
        if team not in ['Blue', 'Red']:
            await ctx.send("Please bet on either 'blue' or 'red'")
            return

        # Create the bet
        self.betting_pool.bets[user_id] = Bet(
            user_id=user_id,
            username=ctx.author.name,
            amount=amount,
            team=team,
            timestamp=time.time()
        )

        # Update totals
        if team == 'Blue':
            self.betting_pool.total_blue += amount
        else:
            self.betting_pool.total_red += amount

        # Track statistics
        if isinstance(self.user_points.get(user_id), Player):
            player = self.user_points[user_id]
            player.total_bets += 1
            player.biggest_bet = max(player.biggest_bet, amount)
            player.points -= amount
            player.username = ctx.author.name  # Always update username
        else:
            # Old format - just update points
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
        losing_bets = [bet for bet in self.betting_pool.bets.values() if bet.team != winner]
        
        # Send a single summary message first
        if winning_bets:
            await self.get_channel(self.channel).send(f"Results for {winner} victory:")
        
        # Process each winner
        for bet in winning_bets:
            share = bet.amount / winning_pool
            winnings = bet.amount + int(losing_pool * share)
            
            # Update points with compatibility for both formats
            if isinstance(self.user_points.get(bet.user_id), Player):
                player = self.user_points[bet.user_id]
                profit = winnings - bet.amount
                player.points += winnings
                player.wins += 1
                player.biggest_win = max(player.biggest_win, profit)
                player.username = bet.username  # Ensure username is current
            else:
                # Old format
                current_points = self.user_points.get(bet.user_id, 0)
                self.user_points[bet.user_id] = current_points + winnings
            
            # Single announcement per winner
            await self.get_channel(self.channel).send(
                f"@{bet.username} won {winnings} pounds! (Bet: {bet.amount}, Bonus: {int(losing_pool * share)})"
            )
        
        # Track losses for losing bets
        for bet in losing_bets:
            if isinstance(self.user_points.get(bet.user_id), Player):
                player = self.user_points[bet.user_id]
                player.losses += 1
                player.biggest_loss = max(player.biggest_loss, bet.amount)

        # Save updated points
        self.save_points()
        self.betting_pool = None  # Clear betting pool after resolution
        return True
    

    @commands.command(name='salt')
    async def points_command(self, ctx):
        """Check your current points"""
        user_id = str(ctx.author.id)
        
        # Get points with compatibility for both formats
        points = self.get_player_points(user_id)
        
        # Get player age if available
        age = "Dark"
        if user_id in self.user_points:
            player = self.user_points[user_id]
            if isinstance(player, Player):
                age = player.age
        
        # Display points with age
        await ctx.send(f"@{ctx.author.name} [{age} Age] you have {points} pounds of salt!")

    @commands.command(name='help')
    async def help_command(self, ctx):
        """Show available commands in Twitch-friendly format"""
        
        # Core betting commands
        await ctx.send("💰 BETTING: !bet <amount> <blue/red> · !mybet · !pool")
        
        # Age advancement system
        await ctx.send("🏰 AGES: !pound to claim salt · !salt to check balance · !advance to level up · !ages for info")
        
        # Stats and results
        await ctx.send("📊 STATS: !stats for your stats · !winners · !losers · !leaderboard for rankings")
        
        # More help
        await ctx.send("ℹ️ Need more info? Try !helpbet or !helpages for detailed command help")
            
    @commands.command(name='helpages')
    async def help_ages_command(self, ctx):
        """Detailed help for the age advancement system"""
        
        await ctx.send("🏰 AGE ADVANCEMENT SYSTEM 🏰")
        await ctx.send("Advance through ages to get better rewards and shorter cooldowns!")
        await ctx.send("!advance - Level up to the next age (costs salt)")
        await ctx.send("!ages - View advancement costs and benefits")
        await ctx.send("!pound - Claim salt (rewards scale with your age)")
        await ctx.send("!salt - Check your current salt balance")
        await ctx.send("!stats - View your age, salt, and other statistics")

    @commands.command(name='helpbet')
    async def help_bet_command(self, ctx):
        """Detailed help for betting system"""
        
        await ctx.send("💰 BETTING SYSTEM 💰")
        await ctx.send("!bet <amount> <blue/red> - Place a bet (also works as !bet blue 100)")
        await ctx.send("!mybet - View your current bet and potential winnings")
        await ctx.send("!pool - See current betting pool sizes and odds")
        await ctx.send("!winners - See biggest winners from last round")
        await ctx.send("!losers - See biggest losers from last round")
   
   
   
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


    @commands.command(name='stats')
    async def stats_command(self, ctx):
        """Show user statistics with age"""
        user_id = str(ctx.author.id)
        if user_id not in self.user_points:
            await ctx.send(f"@{ctx.author.name} No stats available.")
            return
            
        player = self.user_points[user_id]
        age = getattr(player, 'age', "Dark")
        
        await ctx.send(
            f"@{ctx.author.name} [{age} Age] | Salt: {player.points} | "
            f"W/L: {player.wins}/{player.losses} | "
            f"Biggest Win: {player.biggest_win}"
        )

    @commands.command(name='leaderboard')
    async def leaderboard_command(self, ctx):
        """Show top 5 players by points"""
        # Get players in new format
        valid_players = {k: v for k, v in self.user_points.items() 
                        if isinstance(v, Player) and not k.startswith('house_')}
        
        # Sort by points
        top_players = sorted(valid_players.values(), key=lambda p: p.points, reverse=True)[:5]
        
        if not top_players:
            await ctx.send("No players on the leaderboard yet!")
            return
            
        message = "🏆 SALT LEADERBOARD 🏆\n"
        for i, player in enumerate(top_players, 1):
            message += f"{i}. {player.username}: {player.points} salt\n"
            
        await ctx.send(message)

    @commands.command(name='winners')
    async def winners_command(self, ctx):
        """Show biggest winners from last betting round"""
        if not hasattr(self, 'last_round_results'):
            await ctx.send("No completed betting rounds yet!")
            return
        
        # Make sure we're working with a list
        if not isinstance(self.last_round_results, list):
            await ctx.send("No results data available!")
            return
            
        # Sort results by profit
        sorted_winners = sorted(
            self.last_round_results,
            key=lambda x: x.get('profit', 0) if isinstance(x, dict) else 0,
            reverse=True
        )[:3]
        
        if not sorted_winners:
            await ctx.send("No winners from last round!")
            return
        
        entries = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, result in enumerate(sorted_winners):
            if isinstance(result, dict) and result.get('profit', 0) > 0:  # Only show actual winners
                entries.append(
                    f"{medals[i]} {result.get('username', 'Unknown')}: +{result.get('profit', 0):,} 🧂"
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
        
        # Make sure we're working with a list
        if not isinstance(self.last_round_results, list):
            await ctx.send("No results data available!")
            return
            
        # Sort results by profit (ascending for losers)
        sorted_losers = sorted(
            self.last_round_results,
            key=lambda x: x.get('profit', 0) if isinstance(x, dict) else 0
        )[:3]
        
        if not sorted_losers:
            await ctx.send("No results from last round!")
            return
        
        entries = []
        medals = ["💀", "☠️", "👻"]  # Funny emojis for losers
        
        for i, result in enumerate(sorted_losers):
            if isinstance(result, dict) and result.get('profit', 0) < 0:  # Only show actual losers
                entries.append(
                    f"{medals[i]} {result.get('username', 'Unknown')}: {result.get('profit', 0):,} 🧂"
                )
        
        if entries:
            await ctx.send("BIGGEST LOSSES:\n" + "\n".join(entries))
        else:
            await ctx.send("No losses last round!")



    # @commands.command(name='units')
    # async def civs_command(self, ctx):
    #     """Show available unit specializations"""
    #     basic_info = "⚔️ AVAILABLE UNITS (200 salt to pick) ⚔️"
        
    #     unit_list = (
    #         f"{self.civ_manager.CIVILIZATIONS['archer'].badge} Archer: +30% !pound rewards\n"
    #         f"{self.civ_manager.CIVILIZATIONS['infantry'].badge} Infantry: 40% faster !pound cooldown\n"
    #         f"{self.civ_manager.CIVILIZATIONS['cavalry'].badge} Cavalry: Double rewards, 50% longer cooldown\n"
    #         f"{self.civ_manager.CIVILIZATIONS['eagle'].badge} Eagle: 30% cheaper techs"
    #     )

    #     await ctx.send(basic_info)
    #     await ctx.send(unit_list)

    # @commands.command(name='unit')
    # async def civ_command(self, ctx, unit_type: str = None):
    #     """Select or view unit type"""
    #     user_id = str(ctx.author.id)
        
    #     # If no unit specified, show current unit
    #     if not unit_type:
    #         current_unit = self.civ_manager.get_user_civ(user_id)
    #         if current_unit:
    #             await ctx.send(f"@{ctx.author.name} You are specialized in {current_unit.name} {current_unit.badge}")
    #         else:
    #             await ctx.send(f"@{ctx.author.name} You haven't selected a unit type yet. Use !units to see options")
    #         return

    #     # Force lowercase for consistency with our stored values
    #     unit_type = unit_type.lower()

    #     # Check if user already has a unit type
    #     current_unit = self.civ_manager.get_user_civ(user_id)
    #     cost = 1000 if current_unit else 200  # Switch cost vs initial cost
        
    #     # Check if user has enough salt
    #     if self.user_points.get(user_id, 0) < cost:
    #         await ctx.send(f"@{ctx.author.name} You need {cost} salt to {'switch unit type' if current_unit else 'select a unit type'}")
    #         return

    #     # Try to select unit type
    #     success, message = self.civ_manager.select_civilization(user_id, unit_type)
    #     if success:
    #         # Deduct salt
    #         self.user_points[user_id] = self.user_points.get(user_id, 0) - cost
    #         await ctx.send(f"@{ctx.author.name} {message} (-{cost} salt)")
    #         self.save_points()
    #     else:
    #         await ctx.send(f"@{ctx.author.name} {message}")

    #         # Check if user already has a civ
    #         current_civ = self.civ_manager.get_user_civ(user_id)
    #         cost = 1000 if current_civ else 200  # Switch cost vs initial cost
            
    #         # Check if user has enough salt
    #         if self.user_points.get(user_id, 0) < cost:
    #             await ctx.send(f"@{ctx.author.name} You need {cost} salt to {'switch civilizations' if current_civ else 'select a civilization'}")
    #             return

    #         # Try to select civilization
    #         success, message = self.civ_manager.select_civilization(user_id, civilization)
    #         if success:
    #             # Deduct salt
    #             self.user_points[user_id] = self.user_points.get(user_id, 0) - cost
    #             await ctx.send(f"@{ctx.author.name} {message} (-{cost} salt)")
    #             self.save_points()
    #         else:
    #             await ctx.send(f"@{ctx.author.name} {message}")
    @commands.command(name='profile')
    async def profile_command(self, ctx):
        """Show player profile in a single, condensed message"""
        user_id = str(ctx.author.id)
        
        if user_id not in self.user_points:
            await ctx.send(f"@{ctx.author.name} No profile found. Get started with !pound to claim salt!")
            return
        
        player = self.user_points[user_id]
        
        if not isinstance(player, Player):
            # Convert old format for display purposes
            points = player
            age = "Dark"
            wins = 0
            losses = 0
            biggest_win = 0
            biggest_loss = 0
        else:
            # Use Player object data
            points = player.points
            age = player.age
            wins = player.wins
            losses = player.losses
            biggest_win = player.biggest_win
            biggest_loss = player.biggest_loss
        
        # Calculate win rate
        total_bets = wins + losses
        win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
        
        # Format a single, condensed message
        betting_stats = f" | W/L: {wins}/{losses}" if total_bets > 0 else ""
        winrate_stats = f" ({win_rate:.1f}%)" if total_bets > 0 else ""
        
        record_stats = ""
        if total_bets > 0:
            record_stats = f" | Best Win: {biggest_win:,} | Worst Loss: {biggest_loss:,}"
        
        message = f"@{ctx.author.name} [{age} Age] Salt: {points:,}{betting_stats}{winrate_stats}{record_stats}"
        
        await ctx.send(message)