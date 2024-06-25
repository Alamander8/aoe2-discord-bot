import discord
from discord.ext import commands
import requests
import json
import openai
import logging
import asyncio

# Initialize the Discord bot
bot = commands.Bot(command_prefix='!')

# Load AoE2 data from a JSON file
with open('aoe2_data.json', 'r') as f:
    aoe2_data = json.load(f)

# Function to fetch player winrate profiles from AoE2.net API
def get_player_profile(profile_id):
    api_url = f"https://aoe2.net/api/player/profile?game=aoe2de&profile_id={profile_id}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        profile = {
            "name": data['name'],
            "country": data['country'],
            "games": data['games'],
            "wins": data['wins'],
            "losses": data['losses'],
            "winrate": data['win_rate'],
            "favorite_civ": data['favorite_civ']
        }
        return profile
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching player profile: {str(e)}")
        return None

# Command to get civilization information
@bot.command(name='civ')
async def civ(ctx, *, civilization: str):
    civ_info = aoe2_data.get(civilization.lower())
    if civ_info:
        bonuses = "\n".join(civ_info['bonuses'])
        unique_units = ", ".join(civ_info['unique_units'])
        hidden_stats = "\n".join(civ_info['hidden_stats'])
        
        response = f"**{civilization} Civilization**\n\n**Bonuses:**\n{bonuses}\n\n**Unique Units:**\n{unique_units}\n\n**Hidden Stats:**\n{hidden_stats}"
        await ctx.send(response)
    else:
        await ctx.send(f"Sorry, I couldn't find information on the civilization '{civilization}'.")

# Command to get matchup insights
@bot.command(name='matchup')
async def matchup(ctx, *, civilizations: str):
    try:
        civ1, civ2 = [civ.strip().lower() for civ in civilizations.split('vs')]
        civ1_info = aoe2_data.get(civ1)
        civ2_info = aoe2_data.get(civ2)
        
        if civ1_info and civ2_info:
            response = f"**Matchup: {civ1.title()} vs {civ2.title()}**\n\n"
            response += f"**{civ1.title()} Bonuses:**\n" + "\n".join(civ1_info['bonuses']) + "\n\n"
            response += f"**{civ2.title()} Bonuses:**\n" + "\n".join(civ2_info['bonuses']) + "\n\n"
            response += "Strategic Insights:\n"
            await ctx.send(response)
        else:
            await ctx.send("Sorry, I couldn't find information on one or both civilizations.")
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

# Command to get player profile
@bot.command(name='profile')
async def profile(ctx, *, profile_id: int):
    profile = get_player_profile(profile_id)
    if profile:
        response = f"**Player Profile: {profile['name']}**\n\n"
        response += f"**Country:** {profile['country']}\n"
        response += f"**Games Played:** {profile['games']}\n"
        response += f"**Wins:** {profile['wins']}\n"
        response += f"**Losses:** {profile['losses']}\n"
        response += f"**Winrate:** {profile['winrate']}%\n"
        response += f"**Favorite Civilization:** {profile['favorite_civ']}\n"
        await ctx.send(response)
    else:
        await ctx.send("Sorry, I couldn't fetch the profile information.")

# Command to get strategic advice based on player match data
@bot.command(name='advice')
async def advice(ctx, player_id: int):
    """
    Command to get strategic advice based on player match data.
    """
    try:
        match_history_url = f"https://aoe2.net/api/player/matches?game=aoe2de&profile_id={player_id}&count=5"
        match_response = requests.get(match_history_url)
        match_response.raise_for_status()
        matches = match_response.json()
        
        # Summarize match data for GPT input
        match_summaries = "\n".join([f"Opponent: {match['opponent_name']}, Result: {'Win' if match['won'] else 'Loss'}, Civ: {match['civ']}" for match in matches])
        prompt = f"Given the recent match data:\n{match_summaries}\nProvide detailed strategic advice for the player."
        
        gpt_response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=150
        )
        advice = gpt_response.choices[0].text.strip()
        await ctx.send(f"**Strategic Advice:**\n{advice}")
    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error fetching match data: {str(e)}")
    except Exception as e:
        await ctx.send(f"Error generating advice: {str(e)}")

# Command to get lore and backstory for a civilization
@bot.command(name='lore')
async def lore(ctx, *, civilization: str):
    """
    Command to get lore and backstory for a civilization.
    """
    prompt = f"Create an immersive lore and backstory for the civilization: {civilization} in Age of Empires II."
    
    try:
        gpt_response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=300
        )
        lore = gpt_response.choices[0].text.strip()
        await ctx.send(f"**{civilization} Lore:**\n{lore}")
    except Exception as e:
        await ctx.send(f"Error generating lore: {str(e)}")

# Command to generate a custom scenario idea
@bot.command(name='scenario')
async def scenario(ctx):
    """
    Command to generate a custom scenario idea.
    """
    prompt = "Generate a unique custom scenario idea for Age of Empires II, including mission objectives, storyline, and unique challenges."
    
    try:
        gpt_response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=250
        )
        scenario = gpt_response.choices[0].text.strip()
        await ctx.send(f"**Custom Scenario Idea:**\n{scenario}")
    except Exception as e:
        await ctx.send(f"Error generating scenario: {str(e)}")

# Command to get a detailed build order for a specific strategy
@bot.command(name='buildorder')
async def buildorder(ctx, *, strategy_name: str):
    """
    Command to get a detailed build order for a specific strategy.
    """
    build_orders = {
        "fast castle": "1. 6 Sheep\n2. 4 Wood\n3. 1 Boar\n4. 3 Berries\n5. 1 Boar\n6. 2 Farms\n7. 4 Gold\n8. Click up to Feudal\n9. Build Market and Blacksmith\n10. Click up to Castle",
        "drush fc": "1. 6 Sheep\n2. 4 Wood\n3. 1 Boar\n4. 3 Berries\n5. 1 Boar\n6. 2 Farms\n7. 3 Militia\n8. 4 Gold\n9. Click up to Feudal\n10. Build Market and Blacksmith\n11. Click up to Castle",
        "scout rush": "1. 6 Sheep\n2. 4 Wood\n3. 1 Boar\n4. 3 Berries\n5. 1 Boar\n6. 2 Farms\n7. 5 Wood\n8. Click up to Feudal\n9. Build Barracks and Stable\n10. Train Scouts"
    }
    
    build_order = build_orders.get(strategy_name.lower())
    if build_order:
        await ctx.send(f"**{strategy_name.title()} Build Order:**\n{build_order}")
    else:
        await ctx.send("Sorry, I couldn't find that build order. Try 'fast castle', 'drush fc', or 'scout rush'.")

# Command to set reminders at specific intervals
@bot.command(name='reminder')
async def reminder(ctx, interval: int):
    """
    Command to set reminders at specific intervals.
    """
    reminders = [
        "Don't forget to build houses!",
        "Keep creating villagers!",
        "Scout your enemy!",
        "Build farms before your sheep run out!",
        "Transition to the next age when you have enough resources!"
    ]
    
    async def send_reminders():
        for reminder in reminders:
            await ctx.send(reminder)
            await asyncio.sleep(interval * 60)  # Wait for the specified interval in minutes
    
    bot.loop.create_task(send_reminders())

# Adding asyncio to the imports
import asyncio

# Run the bot
bot.run('your_discord_bot_token')
